from __future__ import annotations

import math

# Constants
GRAVITY = 9.8067  # m/s^2
AIR_DENSITY = 1.225  # kg/m^3
CDA = 0.32  # drag coefficient * frontal area (m^2) — typical road cyclist
CRR = 0.005  # coefficient of rolling resistance — typical road tyre
BIKE_MASS = 9.0  # kg — bike + gear


def required_power(
    gradient: float,
    speed: float,
    rider_mass: float,
    bike_mass: float = BIKE_MASS,
    crr: float = CRR,
    cda: float = CDA,
) -> float:
    """Calculate power (watts) required to maintain speed on a gradient.

    Args:
        gradient: grade as fraction (0.05 = 5%)
        speed: m/s
        rider_mass: kg
        bike_mass: kg
        crr: rolling resistance coefficient
        cda: drag area (m^2)
    """
    total_mass = rider_mass + bike_mass
    slope_angle = math.atan(gradient)
    f_gravity = GRAVITY * total_mass * math.sin(slope_angle)
    f_rolling = GRAVITY * total_mass * crr * math.cos(slope_angle)
    f_aero = 0.5 * AIR_DENSITY * cda * speed * speed
    force = f_gravity + f_rolling + f_aero
    power = force * speed
    return max(power, 0.0)


def speed_from_power(
    power: float,
    gradient: float,
    rider_mass: float,
    bike_mass: float = BIKE_MASS,
    crr: float = CRR,
    cda: float = CDA,
    max_iters: int = 50,
    tol: float = 0.001,
) -> float:
    """Solve for speed given power and gradient using Newton's method.

    Returns speed in m/s.
    """
    total_mass = rider_mass + bike_mass
    slope_angle = math.atan(gradient)
    f_gravity = GRAVITY * total_mass * math.sin(slope_angle)
    f_rolling = GRAVITY * total_mass * crr * math.cos(slope_angle)
    resistive = f_gravity + f_rolling

    # Initial guess — on downhill, start from freewheel speed (where
    # gravity balances aero drag at zero power) to avoid Newton's method
    # getting stuck in the wrong region of the cubic.
    aero_coeff = 0.5 * AIR_DENSITY * cda
    if resistive < 0 and aero_coeff > 0:
        v_freewheel = math.sqrt(-resistive / aero_coeff)
        v = v_freewheel + 2.0
    elif power > 0:
        v = 5.0
    else:
        v = 0.1

    for _ in range(max_iters):
        f_aero = 0.5 * AIR_DENSITY * cda * v * v
        total_force = resistive + f_aero
        f_v = total_force * v - power  # We want this to be 0
        # Derivative: d/dv [total_force * v] = resistive + 1.5 * rho * cda * v^2
        df_v = resistive + 1.5 * AIR_DENSITY * cda * v * v
        if abs(df_v) < 1e-12:
            break
        v_new = v - f_v / df_v
        v_new = max(v_new, 0.1)  # Don't go negative
        if abs(v_new - v) < tol:
            v = v_new
            break
        v = v_new

    return max(v, 0.0)


def ftms_grade_from_gradient(percent: float) -> int:
    """Convert gradient percentage to FTMS simulation parameter.

    FTMS uses units of 0.01% — so 10% gradient = 1000.
    Clamped to FTMS range of -40% to +40%.
    """
    clamped = max(-40.0, min(40.0, percent))
    return int(round(clamped * 100))


def effort_fraction(power: float, ftp: int) -> float:
    """Calculate effort as fraction of FTP (0.0-1.0+).

    Used to drive HR simulation and perceived effort.
    """
    if ftp <= 0:
        return 0.0
    return max(0.0, power / ftp)
