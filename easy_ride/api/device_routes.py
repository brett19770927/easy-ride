from __future__ import annotations

from fastapi import APIRouter, HTTPException

from easy_ride.api.schemas import DeviceScanResponse, DiscoveredDeviceResponse

router = APIRouter(prefix="/api")


@router.get("/devices/scan", response_model=DeviceScanResponse)
async def scan_devices():
    try:
        from easy_ride.ble.scanner import scan_for_devices

        devices = await scan_for_devices()
        return DeviceScanResponse(
            devices=[
                DiscoveredDeviceResponse(
                    address=d.address,
                    name=d.name,
                    device_type=d.device_type.value,
                    rssi=d.rssi,
                )
                for d in devices
            ]
        )
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="BLE scanning not available — bleak not installed",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BLE scan failed: {e}")
