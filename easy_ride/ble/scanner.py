from __future__ import annotations

from easy_ride.ble.device_types import DeviceType, DiscoveredDevice

# FTMS (Fitness Machine Service) UUID
FTMS_UUID = "00001826-0000-1000-8000-00805f9b34fb"
# Heart Rate Service UUID
HRS_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
# Cycling Power Service UUID
CPS_UUID = "00001818-0000-1000-8000-00805f9b34fb"


def _classify_device(service_uuids: list[str]) -> DeviceType:
    uuids_lower = [u.lower() for u in service_uuids]
    if FTMS_UUID in uuids_lower or CPS_UUID in uuids_lower:
        return DeviceType.TRAINER
    if HRS_UUID in uuids_lower:
        return DeviceType.HRM
    return DeviceType.UNKNOWN


async def scan_for_devices(timeout: float = 5.0) -> list[DiscoveredDevice]:
    """Scan for BLE fitness devices.

    Returns a list of discovered devices with type classification.
    """
    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    results = []
    for device, adv_data in devices.values():
        service_uuids = adv_data.service_uuids or []
        device_type = _classify_device(service_uuids)
        if device_type == DeviceType.UNKNOWN:
            continue  # Only return fitness-related devices
        results.append(DiscoveredDevice(
            address=device.address,
            name=device.name or "Unknown",
            device_type=device_type,
            rssi=adv_data.rssi or -100,
        ))
    results.sort(key=lambda d: d.rssi, reverse=True)
    return results
