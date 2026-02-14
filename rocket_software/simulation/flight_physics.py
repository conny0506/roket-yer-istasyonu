"""Katman 1 (Euler) ve Katman 2 (RK4) fizik motoru — saf fonksiyonlar, yan etki yok."""

import numpy as np
from .constants import (
    G0, R_EARTH, RHO0, T0, L,
    CD, CROSS_SECTION_AREA,
    DRY_MASS, PROPELLANT_MASS, BURN_TIME,
    DEFAULT_THRUST_CURVE,
)


def gravity(altitude: float) -> float:
    """İrtifaya göre yerçekimi ivmesi (m/s²)."""
    return G0 * (R_EARTH / (R_EARTH + max(altitude, 0.0))) ** 2


def air_density(altitude: float) -> float:
    """ISA troposfer modeli ile hava yoğunluğu (kg/m³)."""
    h = max(altitude, 0.0)
    temp = T0 - L * h
    if temp <= 0:
        return 0.0
    return RHO0 * (temp / T0) ** 4.256


def drag_force(velocity: float, altitude: float,
               cd: float = CD, area: float = CROSS_SECTION_AREA) -> float:
    """Aerodinamik sürüntü kuvveti (N). Hız yönüne ters etki eder."""
    rho = air_density(altitude)
    return 0.5 * rho * velocity ** 2 * cd * area


def _build_thrust_interpolator(thrust_curve):
    """İtki eğrisini numpy interpolasyon için hazırlar."""
    times = np.array([p[0] for p in thrust_curve], dtype=float)
    forces = np.array([p[1] for p in thrust_curve], dtype=float)
    return times, forces


def thrust_at_time(t: float, thrust_curve=None) -> float:
    """Verilen zamanda motor itkisi (N). Yanma bittikten sonra 0 döner."""
    if thrust_curve is None:
        thrust_curve = DEFAULT_THRUST_CURVE
    times, forces = _build_thrust_interpolator(thrust_curve)
    if t < times[0] or t > times[-1]:
        return 0.0
    return float(np.interp(t, times, forces))


def current_mass(t: float, dry_mass: float = DRY_MASS,
                 propellant_mass: float = PROPELLANT_MASS,
                 burn_time: float = BURN_TIME) -> float:
    """Anlık kütle (kg). Yakıt yandıkça azalır."""
    fuel_fraction = max(0.0, 1.0 - t / burn_time)
    return dry_mass + propellant_mass * fuel_fraction


def net_acceleration(t: float, velocity: float, altitude: float,
                     thrust_curve=None,
                     dry_mass: float = DRY_MASS,
                     propellant_mass: float = PROPELLANT_MASS,
                     burn_time: float = BURN_TIME,
                     cd: float = CD,
                     area: float = CROSS_SECTION_AREA) -> float:
    """Net dikey ivme (m/s²). Pozitif → yukarı."""
    m = current_mass(t, dry_mass, propellant_mass, burn_time)
    f_thrust = thrust_at_time(t, thrust_curve)
    f_drag = drag_force(velocity, altitude, cd, area)
    f_grav = gravity(altitude) * m

    # Sürüntü hızla zıt yönde; roket yükselirken hız pozitif, drag aşağı
    drag_sign = -1.0 if velocity >= 0 else 1.0
    f_net = f_thrust + drag_sign * f_drag - f_grav
    return f_net / m


def integrate_euler(t: float, altitude: float, velocity: float,
                    dt: float, **kwargs) -> tuple:
    """Euler yöntemi ile bir zaman adımı ilerle. (t, h, v, a) döner."""
    a = net_acceleration(t, velocity, altitude, **kwargs)
    v_new = velocity + a * dt
    h_new = altitude + velocity * dt
    if h_new < 0.0:
        h_new = 0.0
        v_new = 0.0  # zemine çarptı, hareket durdu
    return t + dt, h_new, v_new, a


def integrate_euler_2d(t: float, x: float, z: float,
                       vx: float, vz: float, dt: float,
                       tilt_rad: float,
                       thrust_curve=None,
                       dry_mass: float = DRY_MASS,
                       propellant_mass: float = PROPELLANT_MASS,
                       burn_time: float = BURN_TIME,
                       cd: float = CD,
                       area: float = CROSS_SECTION_AREA) -> tuple:
    """2D Euler — yatay (x) + dikey (z) eksenli.

    tilt_rad: dikeyden sapma açısı (0 = düz yukarı).
    Thrust roket gövdesi boyunca etki eder (tilt yönünde).
    Drag, toplam hız vektörüne ters etki eder.
    Yerçekimi sadece z'ye.

    Döner: (t+dt, x_new, z_new, vx_new, vz_new, a_axial_ms2)
    """
    import math
    m = current_mass(t, dry_mass, propellant_mass, burn_time)
    f_thrust = thrust_at_time(t, thrust_curve)

    speed = math.sqrt(vx * vx + vz * vz)
    rho = air_density(z)
    f_drag = 0.5 * rho * speed * speed * cd * area

    # Thrust bileşenleri (tilt dikeyden)
    fx_thrust = f_thrust * math.sin(tilt_rad)
    fz_thrust = f_thrust * math.cos(tilt_rad)

    # Drag bileşenleri (hız yönüne ters)
    if speed > 1e-6:
        fx_drag = -f_drag * vx / speed
        fz_drag = -f_drag * vz / speed
    else:
        fx_drag = fz_drag = 0.0

    fz_grav = -gravity(z) * m

    ax = (fx_thrust + fx_drag) / m
    az = (fz_thrust + fz_drag + fz_grav) / m

    vx_new = vx + ax * dt
    vz_new = vz + az * dt
    x_new = x + vx * dt
    z_new = z + vz * dt

    if z_new < 0.0:
        z_new = 0.0
        vx_new = 0.0
        vz_new = 0.0

    # Eksen ivmesi (gövde boyunca — sensör okuması için)
    a_axial = (ax * math.sin(tilt_rad) + az * math.cos(tilt_rad))
    # Toplam ivme büyüklüğü (sensör magnitude / FSM için — rest'te ≈ g)
    a_total = math.sqrt(ax * ax + az * az)
    return t + dt, x_new, z_new, vx_new, vz_new, a_axial, a_total


def integrate_rk4(t: float, altitude: float, velocity: float,
                  dt: float, **kwargs) -> tuple:
    """RK4 yöntemi ile bir zaman adımı ilerle. (t, h, v, a) döner."""
    def deriv(ti, hi, vi):
        ai = net_acceleration(ti, vi, hi, **kwargs)
        return vi, ai  # dh/dt = v, dv/dt = a

    v1, a1 = deriv(t, altitude, velocity)
    v2, a2 = deriv(t + dt / 2, altitude + dt / 2 * velocity, velocity + dt / 2 * a1)
    v3, a3 = deriv(t + dt / 2, altitude + dt / 2 * v2, velocity + dt / 2 * a2)
    v4, a4 = deriv(t + dt, altitude + dt * v3, velocity + dt * a3)

    h_new = altitude + (dt / 6) * (v1 + 2 * v2 + 2 * v3 + v4)
    v_new = velocity + (dt / 6) * (a1 + 2 * a2 + 2 * a3 + a4)
    a_avg = (a1 + 2 * a2 + 2 * a3 + a4) / 6
    if h_new < 0.0:
        h_new = 0.0
        v_new = 0.0  # zemine çarptı, hareket durdu
    return t + dt, h_new, v_new, a_avg
