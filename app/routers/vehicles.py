# app/routers/vehicles.py
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from urllib.parse import quote 
import httpx
from typing import Optional
from pydantic import BaseModel, Field
from app.database import get_db

from app.models import User, Vehicle
from app.schemas import VehicleCreate, VehicleUpdate, VehicleResponse
from app.auth import get_current_customer

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


# Add these helper functions after your existing VIN functions

async def search_location_by_address(address: str, city: str = None, state: str = None, zipcode: str = None):
    """Search location details using address components - CORRECTED VERSION"""
    
    # Build search query
    search_parts = [address]
    if city:
        search_parts.append(city)
    if state:
        search_parts.append(state)
    if zipcode:
        search_parts.append(zipcode)
    
    # Join parts and then URL-encode the entire query
    raw_query = ", ".join(filter(None, search_parts))
    # Use `from urllib.parse import quote` at the top of your file
    encoded_query = quote(raw_query) 
    
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_query}&format=json&limit=1&addressdetails=1"
    
    # --- THE MOST IMPORTANT FIX: A VALID USER-AGENT ---
    headers = {
        "User-Agent": "MyTowingServiceApp/1.0 (contact@yourdomain.com)"  # <-- REPLACE WITH YOUR INFO
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Pass the headers in the request
            response = await client.get(url, headers=headers) 
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                result = data[0]
                address_details = result.get("address", {})
                
                return {
                    "success": True,
                    "latitude": float(result["lat"]),
                    "longitude": float(result["lon"]),
                    "address": result.get("display_name", ""),
                    "city": address_details.get("city") or address_details.get("town") or address_details.get("village", ""),
                    "state": address_details.get("state", ""),
                    "zipcode": address_details.get("postcode", ""),
                    "country": address_details.get("country", ""),
                    "landmark": address_details.get("suburb") or address_details.get("neighbourhood", "")
                }
            return {"success": False, "error": "Location not found"}
        except Exception as e:
            return {"success": False, "error": f"Search failed: {str(e)}"}

async def search_location_by_zipcode(zipcode: str):
    """Search location using zipcode only - FULLY CORRECTED"""
    
    # Clean and encode the zipcode
    zipcode = str(zipcode).strip()
    encoded_zipcode = quote(zipcode, safe='')
    
    # Build the URL with properly encoded parameters
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_zipcode}&format=json&limit=1&addressdetails=1&countrycodes=us"
    
    # CRITICAL: Use a REAL, UNIQUE user-agent (not generic!)
    headers = {
        "User-Agent": "MyTowingService/1.0 (https://yourwebsite.com; support@yourwebsite.com)",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            # Log the response for debugging
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                result = data[0]
                address_details = result.get("address", {})
                
                return {
                    "success": True,
                    "latitude": float(result["lat"]),
                    "longitude": float(result["lon"]),
                    "address": result.get("display_name", ""),
                    "city": address_details.get("city") or address_details.get("town", ""),
                    "state": address_details.get("state", ""),
                    "zipcode": zipcode,
                    "country": address_details.get("country", "")
                }
            
            return {"success": False, "error": f"Zipcode '{zipcode}' not found"}
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            print(f"Error: {str(e)}")
            return {"success": False, "error": f"Request failed: {str(e)}"}

# --- Location Auto-Fetch GET Endpoints ---

@router.get("/location/search")
async def search_location(
    address: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zipcode: Optional[str] = None
):
    """
    Auto-fetch location details using any combination of:
    - address
    - city
    - state
    - zipcode
    
    Example: 
    /vehicles/location/search?address=Times Square&city=New York&state=NY
    /vehicles/location/search?zipcode=10036
    """
    
    # If zipcode provided, use zipcode search
    if zipcode:
        result = await search_location_by_zipcode(zipcode)
    else:
        # Use address search
        if not address:
            raise HTTPException(status_code=400, detail="Either address or zipcode is required")
        result = await search_location_by_address(address, city, state, zipcode)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Location not found"))
    
    return {
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "address": result.get("address"),
        "landmark": result.get("landmark"),
        "city": result.get("city"),
        "state": result.get("state"),
        "zipcode": result.get("zipcode"),
        "country": result.get("country"),
        "formatted_address": f"{result.get('address', '')}"
    }

@router.get("/location/from-address")
async def get_location_from_address(
    address: str,
    city: Optional[str] = None,
    state: Optional[str] = None
):
    """
    Get complete location details from address
    Returns: latitude, longitude, city, state, zipcode
    """
    
    result = await search_location_by_address(address, city, state)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Address not found"))
    
    return {
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "address": result.get("address"),
        "city": result.get("city"),
        "state": result.get("state"),
        "zipcode": result.get("zipcode")
    }

@router.get("/location/from-zipcode")
async def get_location_from_zipcode(zipcode: str):
    """
    Get location details from zipcode only
    Returns: latitude, longitude, city, state, address
    """
    
    if len(zipcode) not in [5, 9]:
        raise HTTPException(status_code=400, detail="Zipcode must be 5 or 9 digits")
    
    result = await search_location_by_zipcode(zipcode)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Zipcode not found"))
    
    return {
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "address": result.get("address"),
        "city": result.get("city"),
        "state": result.get("state"),
        "zipcode": zipcode
    }

@router.get("/location/from-city-state")
async def get_location_from_city_state(
    city: str,
    state: str
):
    """
    Get location details from city and state
    Returns: latitude, longitude, zipcode, full address
    """
    
    result = await search_location_by_address(city, city, state)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="City/State not found")
    
    return {
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "address": result.get("address"),
        "city": city,
        "state": state,
        "zipcode": result.get("zipcode")
    }

@router.get("/towing/locations/auto-fill")
async def auto_fill_towing_locations(
    from_address: Optional[str] = None,
    from_city: Optional[str] = None,
    from_state: Optional[str] = None,
    from_zipcode: Optional[str] = None,
    from_landmark: Optional[str] = None,
    to_address: Optional[str] = None,
    to_city: Optional[str] = None,
    to_state: Optional[str] = None,
    to_zipcode: Optional[str] = None,
    to_landmark: Optional[str] = None
):
    """
    Auto-fill both from and to locations using address components
    All parameters are optional but at least one location identifier needed
    
    Example:
    /towing/locations/auto-fill?from_address=Times Square&from_city=New York&from_state=NY&to_zipcode=10036
    """
    
    # Process from_location
    from_location = None
    if from_zipcode:
        from_result = await search_location_by_zipcode(from_zipcode)
        if from_result.get("success"):
            from_location = {
                "latitude": from_result.get("latitude"),
                "longitude": from_result.get("longitude"),
                "address": from_result.get("address"),
                "landmark": from_landmark,
                "city": from_result.get("city"),
                "state": from_result.get("state"),
                "zipcode": from_zipcode
            }
    elif from_address:
        from_result = await search_location_by_address(from_address, from_city, from_state)
        if from_result.get("success"):
            from_location = {
                "latitude": from_result.get("latitude"),
                "longitude": from_result.get("longitude"),
                "address": from_result.get("address"),
                "landmark": from_landmark,
                "city": from_result.get("city") or from_city,
                "state": from_result.get("state") or from_state,
                "zipcode": from_result.get("zipcode")
            }
    
    # Process to_location
    to_location = None
    if to_zipcode:
        to_result = await search_location_by_zipcode(to_zipcode)
        if to_result.get("success"):
            to_location = {
                "latitude": to_result.get("latitude"),
                "longitude": to_result.get("longitude"),
                "address": to_result.get("address"),
                "landmark": to_landmark,
                "city": to_result.get("city"),
                "state": to_result.get("state"),
                "zipcode": to_zipcode
            }
    elif to_address:
        to_result = await search_location_by_address(to_address, to_city, to_state)
        if to_result.get("success"):
            to_location = {
                "latitude": to_result.get("latitude"),
                "longitude": to_result.get("longitude"),
                "address": to_result.get("address"),
                "landmark": to_landmark,
                "city": to_result.get("city") or to_city,
                "state": to_result.get("state") or to_state,
                "zipcode": to_result.get("zipcode")
            }
    
    if not from_location:
        raise HTTPException(status_code=400, detail="Could not fetch from_location details")
    if not to_location:
        raise HTTPException(status_code=400, detail="Could not fetch to_location details")
    
    # Calculate distance
    distance_km = calculate_distance(
        from_location.get("latitude"),
        from_location.get("longitude"),
        to_location.get("latitude"),
        to_location.get("longitude")
    )
    
    return {
        "from_location": from_location,
        "to_location": to_location,
        "distance_km": round(distance_km, 2),
        "distance_miles": round(distance_km * 0.621371, 2),
        "estimated_towing_time_minutes": round(distance_km * 1.2, 0)  # Rough estimate: 1.2 min per km
    }

# Add this helper function at the end of your file
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula"""
    from math import radians, sin, cos, sqrt, atan2
    
    if not all([lat1, lon1, lat2, lon2]):
        return 0
    
    R = 6371  # Earth's radius in km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c
# --- Helper Function to Call NHTSA API ---
def validate_vin_format(vin: str) -> bool:
    """Basic VIN format validation"""
    vin = vin.upper()
    
    # VIN must be 17 characters
    if len(vin) != 17:
        return False
    
    # Valid characters: A-Z 0-9 (excluding I, O, Q)
    valid_chars = set('ABCDEFGHJKLMNPRSTUVWXYZ0123456789')
    if not all(c in valid_chars for c in vin):
        return False
    
    return True

async def fetch_vehicle_details_from_vin(vin: str):
    """Calls the NHTSA API to get vehicle details from a VIN."""
    vin = vin.strip().upper()
    
    # Basic validation
    if len(vin) != 17:
        return {"error": "VIN must be exactly 17 characters long."}
    
    if not validate_vin_format(vin):
        return {"error": "VIN contains invalid characters. Valid characters are A-Z (except I, O, Q) and 0-9."}
    
    # Try multiple endpoints for better success rate
    endpoints = [
        f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json",
        f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
    ]
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in endpoints:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                if data.get("Results") and len(data["Results"]) > 0:
                    vehicle_info = data["Results"][0]
                    
                    # Check if we got meaningful data
                    if vehicle_info.get("Make") and vehicle_info.get("Make") != "":
                        return {
                            "success": True,
                            "brand": vehicle_info.get("Make"),
                            "model": vehicle_info.get("Model"),
                            "year": vehicle_info.get("ModelYear"),
                            "vehicle_type": vehicle_info.get("VehicleType", "car").lower(),
                            "body_class": vehicle_info.get("BodyClass"),
                            "manufacturer": vehicle_info.get("Manufacturer")
                        }
                        
            except Exception as e:
                continue  # Try next endpoint
    
    return {"success": False, "error": "Could not decode VIN. Please check if the VIN is valid for US vehicles (1995+)."}

# --- VIN Auto-Fetch Endpoint (NO AUTHENTICATION REQUIRED) ---

@router.get("/detail/{vin}")
async def get_vehicle_details_by_vin(
    vin: str,
    db: Session = Depends(get_db)
):
    """
    Get vehicle details from VIN (No authentication required)
    Fetches from NHTSA API and returns brand, model, year, etc.
    """
    
    # Validate VIN format
    if len(vin) != 17:
        raise HTTPException(status_code=400, detail="VIN must be exactly 17 characters long")
    
    # Fetch from NHTSA API
    api_data = await fetch_vehicle_details_from_vin(vin)
    
    if not api_data.get("success"):
        raise HTTPException(status_code=400, detail=api_data.get("error", "Failed to decode VIN"))
    
    # Return the decoded information with color as null
    return {
        "vin": vin.upper(),
        "brand": api_data.get("brand"),
        "model": api_data.get("model"),
        "year": api_data.get("year"),
        "color": None,  # Color not available from VIN
        "vehicle_type": api_data.get("vehicle_type"),
        "body_class": api_data.get("body_class"),
        "manufacturer": api_data.get("manufacturer"),
        "full_name": f"{api_data.get('year')} {api_data.get('brand')} {api_data.get('model')}" if api_data.get('year') else f"{api_data.get('brand')} {api_data.get('model')}",
        "message": "Color information is not available from VIN. Please add manually."
    }


@router.patch("/{vin}/update-color")
async def update_vehicle_color(
    vin: str,
    color: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer)
):
    """
    Update color for a vehicle (Requires authentication)
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.customer_id == current_user.id,
        Vehicle.vin_number == vin.upper()
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    vehicle.color = color
    db.commit()
    db.refresh(vehicle)
    
    return {
        "message": "Color updated successfully",
        "vin": vehicle.vin_number,
        "color": vehicle.color
    }
# --- OPTIONAL: Save vehicle to database (with authentication) ---
@router.post("/save-from-vin")
async def save_vehicle_from_vin(
    vin: str,
    color: str,
    license_plate: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer)
):
    """
    Save vehicle to user's account (Requires authentication)
    First fetches VIN details, then saves to database
    """
    
    # Fetch VIN details
    api_data = await fetch_vehicle_details_from_vin(vin)
    
    if not api_data.get("success"):
        raise HTTPException(status_code=400, detail=api_data.get("error", "Failed to decode VIN"))
    
    # Check if vehicle already exists for this user
    existing_vehicle = db.query(Vehicle).filter(
        Vehicle.customer_id == current_user.id,
        Vehicle.vin_number == vin.upper()
    ).first()
    
    if existing_vehicle:
        raise HTTPException(status_code=400, detail="Vehicle with this VIN already exists")
    
    # Create new vehicle
    new_vehicle = Vehicle(
        customer_id=current_user.id,
        vin_number=vin.upper(),
        brand=api_data.get("brand"),
        model=api_data.get("model"),
        year=api_data.get("year"),
        vehicle_type=api_data.get("vehicle_type"),
        body_class=api_data.get("body_class"),
        color=color,
        license_plate=license_plate.upper(),
        vehicle_condition="running",
        towing_type="open",
        priority_level="normal",
        is_default=False
    )
    
    # If this is the first vehicle, make it default
    existing_vehicles_count = db.query(Vehicle).filter(Vehicle.customer_id == current_user.id).count()
    if existing_vehicles_count == 0:
        new_vehicle.is_default = True
    
    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)
    
    return {
        "message": "Vehicle saved successfully",
        "vehicle": VehicleResponse.model_validate(new_vehicle)
    }


# --- EXISTING CRUD ENDPOINTS (Require Authentication) ---

@router.get("/", response_model=List[VehicleResponse])
async def get_my_vehicles(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Get all vehicles for current customer"""
    vehicles = db.query(Vehicle).filter(Vehicle.customer_id == current_user.id).all()
    return [VehicleResponse.model_validate(v) for v in vehicles]


@router.post("/", response_model=VehicleResponse)
async def create_vehicle(
    vehicle_data: VehicleCreate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Create a new vehicle"""
    
    new_vehicle = Vehicle(
        customer_id=current_user.id,
        **vehicle_data.model_dump()
    )
    
    # If this is the first vehicle, make it default
    existing_vehicles = db.query(Vehicle).filter(Vehicle.customer_id == current_user.id).count()
    if existing_vehicles == 0:
        new_vehicle.is_default = True
    
    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)
    
    return VehicleResponse.model_validate(new_vehicle)


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Get vehicle by ID"""
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.customer_id == current_user.id
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    return VehicleResponse.model_validate(vehicle)


@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    vehicle_data: VehicleUpdate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Update vehicle details"""
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.customer_id == current_user.id
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    for field, value in vehicle_data.model_dump(exclude_unset=True).items():
        setattr(vehicle, field, value)
    
    db.commit()
    db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: UUID,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Delete a vehicle"""
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.customer_id == current_user.id
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    db.delete(vehicle)
    db.commit()
    
    return {"message": "Vehicle deleted successfully"}


@router.put("/{vehicle_id}/default")
async def set_default_vehicle(
    vehicle_id: UUID,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Set a vehicle as default"""
    
    # Remove default from all other vehicles
    db.query(Vehicle).filter(Vehicle.customer_id == current_user.id).update({"is_default": False})
    
    # Set this vehicle as default
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.customer_id == current_user.id
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    vehicle.is_default = True
    db.commit()
    
    return {"message": "Default vehicle updated successfully"}