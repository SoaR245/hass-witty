"""Constants for witty one read."""

from uuid import UUID


def _info_uuid(address: str) -> UUID:
    return UUID(f"{address}e6d9-4a07-4169-a799-89bc59e4f742")


def _state_uuid(address: str) -> UUID:
    return UUID(f"{address}cf60-ea50-49f9-9471-a3fe0cfce893")


MODEL_UUID = _info_uuid("1400")

NAME_UUID = _state_uuid("0080")

# Version
# app version a.b.c.d _
# length 4+0x0005 format <HBBBBB
PACKAGE_VERSION_UUID = _state_uuid("0002")

# app version a.b.c.d (_) boot version a.b.c.d
# length 4+0x003C format <HBBBBBBBB...
MAIN_BOARD_VERSION_UUID = _state_uuid("0102")
RF_BOARD_VERSION_UUID = _state_uuid("0202")
HMI_BOARD_VERSION_UUID = _state_uuid("0302")

STATE_UUID = _state_uuid("0010")  # length 4+0x0004 format : <HI
STARTUP_COUNT_UUID = _state_uuid("0410")  # length 4+0x0004 format : <HI
DURATIONS_UUID = _state_uuid("0510")  # length 4+0x0010 format : <HIIII
COMMUTATION_UUID = _state_uuid("0610")  # length 4+0x0020 format : <HQQQQ
CAR_DETECT_UUID = _state_uuid("0710")  # length 4+0x0004 format : <HQ
CHARGING_NUMBER_UUID = _state_uuid("0810")  # length 4+0x0004 format : <HQ

MOTOR_LOCK_STATE_UUID = _state_uuid("0c10")  # length 4+0x0002 format : <HH

# Electric
ENERGY_UUID = _state_uuid("4010")
ELECTRIC_STATE_UUID = _state_uuid("4110")
NEUTRAL_VOLTAGE = _state_uuid("4210")

# Temp
AMBIENT_TEMP_UUID = _state_uuid("5010")
RELAY_TEMP_UUID = _state_uuid("5110")
UNK_TEMP_UUID = _state_uuid("5210")

# length 4+0x000C format : <HHHHHHH 0500 1400 1000 0000 0000 0300
CONNECTION_STATE_UUID = _state_uuid("6010")

SESSION_STATE_UUID = _state_uuid("6110")

DATE_STR_UUID = _state_uuid("0120")

# Config
# app "cableLock" config (0=not_locked 1=locked 2=unlocked 3=blocked_locked
# 4=blocked_unlocked 5=blocked), length 4+0x0001 format : <HB
CONFIG_CABLE_LOCK_UUID = _state_uuid("0880")

# app "accessControlMode" config (0=anyone 1=badge_only)
# length 4+0x0001 format : <HB
# NOTE: 2180 holds a badge slot data blob, not the access control mode itself
ACCESS_CONTROL_MODE_UUID = _state_uuid("2080")
CONFIG_BADGE_UUID = _state_uuid("2180")

#  MAC (6 bytes), NAME 32 bytes, STATE 1 byte
CONFIG_ADMIN_PHONES_UUID = _state_uuid("3080")

# app "chargeMode" config, length 4+0x0001 format : <HB
# 1=off 2=boost 3=slow 6=solar 7=solar_eco
CHARGE_MODE_UUID = _state_uuid("6080")

# app "reduceCurrent" (slow mode current limit, A), length 4+0x0002 format : <HH
REDUCE_CURRENT_UUID = _state_uuid("6180")

# app "defaultChargeState" config, length 4+0x0001 format : <HB
DEFAULT_CHARGE_STATE_UUID = _state_uuid("6280")

# app "maxCurrent" (max charging current, A), length 4+0x0002 format : <HH
MAX_CURRENT_UUID = _state_uuid("0180")

# app "fallbackCurrent" (current used when regulation is lost, A)
# length 4+0x0002 format : <HH
FALLBACK_CURRENT_UUID = _state_uuid("8180")
