from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from services.vin_service import vin_decoder

router = APIRouter(prefix="/api/vin", tags=["VIN Decoding"])

class VINDecodeRequest(BaseModel):
    vin: str = Field(..., min_length=17, max_length=17, description="17-character VIN number")
    
    @validator('vin')
    def validate_vin(cls, v):
        v = v.strip().upper()
        # VIN validation regex for US vehicles
        import re
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', v):
            raise ValueError('Invalid VIN format. VIN must be 17 characters containing only letters and numbers (excluding I, O, Q)')
        return v

class VINFullResponse(BaseModel):
    success: bool
    vin: str
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    vehicle_type: Optional[str]
    body_class: Optional[str]
    manufacturer: Optional[str]
    fuel_type: Optional[str]
    engine_size: Optional[str]
    drive_type: Optional[str]
    region_specific: Optional[dict]
    additional_details: Optional[dict]
    error: Optional[str]

@router.get("/decode/{vin}", response_model=VINFullResponse)
async def decode_vin(vin: str):
    """Decode VIN and get complete vehicle information"""
    try:
        result = await vin_decoder.get_vehicle_by_vin_full(vin)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/decode-batch")
async def decode_vins_batch(vins: List[str]):
    """Decode multiple VINs at once (max 50)"""
    if len(vins) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 VINs per batch request")
    
    results = await vin_decoder.batch_decode(vins)
    return results

@router.get("/info/{vin}")
async def get_basic_vehicle_info(vin: str):
    """Get basic vehicle information (brand, model, year only)"""
    result = await vin_decoder.decode_vin(vin)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid VIN"))
    
    return {
        "vin": result["vin"],
        "brand": result["brand"],
        "model": result["model"],
        "year": result["year"],
        "vehicle_type": result["vehicle_type"],
        "full_name": f"{result['year']} {result['brand']} {result['model']}" if result['year'] else f"{result['brand']} {result['model']}"
    }

@router.get("/quick/{vin}")
async def quick_lookup(vin: str):
    """Quick lookup - returns only essential info"""
    result = await vin_decoder.decode_vin(vin)
    
    return {
        "success": result["success"],
        "make": result["brand"],
        "model": result["model"],
        "year": result["year"]
    }

# US-specific endpoints
@router.get("/us/specs/{vin}")
async def get_us_vehicle_specs(vin: str):
    """Get US-specific vehicle specifications"""
    result = await vin_decoder.get_vehicle_by_vin_full(vin)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail="Invalid VIN")
    
    return {
        "vehicle": {
            "year": result.get("year"),
            "make": result.get("brand"),
            "model": result.get("model"),
            "trim": result.get("trim"),
            "body_style": result.get("body_class")
        },
        "us_compliance": {
            "epa_class": result.get("region_specific", {}).get("epa_class"),
            "dmv_category": result.get("region_specific", {}).get("us_dmv_category"),
            "fits_us_roads": True
        },
        "mechanical": {
            "engine": result.get("engine_size"),
            "fuel_type": result.get("fuel_type"),
            "drive_type": result.get("drive_type"),
            "transmission": result.get("transmission")
        },
        "source": "NHTSA VPIC API",
        "last_updated": datetime.utcnow().isoformat()
    }