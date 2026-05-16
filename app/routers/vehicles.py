# app/routers/vehicles.py
import httpx
from fastapi import APIRouter, Depends, HTTPException , Query
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
    zipcode: Optional[str] = None,
    country: Optional[str] = None,  # Added country parameter
    # Field filtering parameters
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return. Options: latitude, longitude, address, landmark, city, state, zipcode, country, formatted_address"),
    exclude_fields: Optional[str] = Query(None, description="Comma-separated list of fields to exclude from response")
):
    """
    Auto-fetch location details using any combination of:
    - address
    - city
    - state
    - zipcode
    - country
    
    Examples:
    - Only city: /vehicles/location/search?city=New York
    - City and state: /vehicles/location/search?city=Los Angeles&state=CA
    - Only state: /vehicles/location/search?state=Texas
    - Only country: /vehicles/location/search?country=United States
    - Full address: /vehicles/location/search?address=Times Square&city=New York&state=NY
    
    Field filtering examples:
    - Get only latitude and longitude: /vehicles/location/search?zipcode=10036&fields=latitude,longitude
    - Exclude landmark and country: /vehicles/location/search?zipcode=10036&exclude_fields=landmark,country
    """
    
    # If zipcode provided, use zipcode search (priority)
    if zipcode:
        result = await search_location_by_zipcode(zipcode)
    else:
        # Build search query from available parameters
        if not any([address, city, state, country]):
            raise HTTPException(status_code=400, detail="At least one of address, city, state, or country is required")
        
        # If only city and/or state provided, use them as address
        if not address and (city or state or country):
            # Build a composite search string
            search_parts = []
            if city:
                search_parts.append(city)
            if state:
                search_parts.append(state)
            if country:
                search_parts.append(country)
            
            search_address = ", ".join(search_parts)
            result = await search_location_by_address(search_address, city, state, zipcode)
        else:
            # Use address search with all parameters
            result = await search_location_by_address(address, city, state, zipcode)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Location not found"))
    
    # Build complete response
    full_response = {
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "address": result.get("address"),
        "landmark": result.get("landmark"),
        "city": result.get("city"),
        "state": result.get("state"),
        "zipcode": result.get("zipcode"),
        "country": result.get("country"),
        "formatted_address": result.get("address", "")
    }
    
    # Apply field filtering
    if fields:
        # Include only specified fields
        field_list = [f.strip() for f in fields.split(",")]
        filtered_response = {k: v for k, v in full_response.items() if k in field_list}
        return filtered_response
    
    if exclude_fields:
        # Exclude specified fields
        exclude_list = [f.strip() for f in exclude_fields.split(",")]
        filtered_response = {k: v for k, v in full_response.items() if k not in exclude_list}
        return filtered_response
    
    # Return all fields if no filtering specified
    return full_response

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
    include_fields: Optional[str] = Query(None, description="Comma-separated fields to include: brand, model, year, color, vehicle_type, body_class, manufacturer, full_name"),
    exclude_fields: Optional[str] = Query(None, description="Comma-separated fields to exclude"),
    db: Session = Depends(get_db)
):
    """
    Get vehicle details from VIN (No authentication required)
    Fetches from NHTSA API and returns brand, model, year, etc.
    
    Filter examples:
    - Only brand and model: /detail/5YJSA1E26HF000337?include_fields=brand,model
    - Exclude color and message: /detail/5YJSA1E26HF000337?exclude_fields=color,message
    - Only brand: /detail/5YJSA1E26HF000337?include_fields=brand
    - Brand with model and year: /detail/5YJSA1E26HF000337?include_fields=brand,model,year
    """
    
    # Validate VIN format
    if len(vin) != 17:
        raise HTTPException(status_code=400, detail="VIN must be exactly 17 characters long")
    
    # Fetch from NHTSA API
    api_data = await fetch_vehicle_details_from_vin(vin)
    
    if not api_data.get("success"):
        raise HTTPException(status_code=400, detail=api_data.get("error", "Failed to decode VIN"))
    
    # Build complete response
    full_response = {
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
    
    # Apply field filtering
    if include_fields:
        # Include only specified fields
        field_list = [f.strip() for f in include_fields.split(",")]
        filtered_response = {k: v for k, v in full_response.items() if k in field_list}
        return filtered_response
    
    if exclude_fields:
        # Exclude specified fields
        exclude_list = [f.strip() for f in exclude_fields.split(",")]
        filtered_response = {k: v for k, v in full_response.items() if k not in exclude_list}
        return filtered_response
    
    # Return all fields if no filtering specified
    return full_response


@router.get("/brands/list")
async def get_available_brands(
    search: Optional[str] = Query(None, description="Search brand by name"),
    limit: int = Query(50, description="Number of brands to return", ge=1, le=200)
):
    """
    Get list of available vehicle brands from NHTSA database
    Returns all car brands with their details
    
    Examples:
    - All brands: /brands/list
    - Search brand: /brands/list?search=toyota
    - Limit results: /brands/list?limit=10
    """
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Fetch all makes from NHTSA API
            url = "https://vpic.nhtsa.dot.gov/api/vehicles/getallmakes?format=json"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data.get("Results"):
                brands = []
                for item in data["Results"]:
                    brand_name = item.get("Make_Name", "")
                    brand_id = item.get("Make_ID", "")
                    
                    brands.append({
                        "brand_id": brand_id,
                        "brand_name": brand_name,
                        "brand_name_lower": brand_name.lower()
                    })
                
                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    brands = [b for b in brands if search_lower in b["brand_name_lower"]]
                
                # Remove the lowercase field from response
                for brand in brands:
                    del brand["brand_name_lower"]
                
                # Apply limit
                brands = brands[:limit]
                
                return {
                    "total_brands": len(brands),
                    "brands": brands
                }
            
            return {"total_brands": 0, "brands": []}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch brands: {str(e)}")


@router.get("/brands/{brand_name}/models")
async def get_models_by_brand(
    brand_name: str,
    year: Optional[int] = Query(None, description="Filter models by year"),
    search: Optional[str] = Query(None, description="Search model by name"),
    limit: int = Query(50, description="Number of models to return", ge=1, le=200)
):
    """
    Get all models for a specific brand
    
    Examples:
    - All Tesla models: /brands/Tesla/models
    - Toyota models from 2020: /brands/Toyota/models?year=2020
    - Search Honda models with 'Civic': /brands/Honda/models?search=civic
    """
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Build URL based on whether year is provided
            if year:
                url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/{brand_name}/modelyear/{year}?format=json"
            else:
                url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformake/{brand_name}?format=json"
            
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data.get("Results"):
                models = []
                for item in data["Results"]:
                    model_name = item.get("Model_Name", "")
                    model_id = item.get("Model_ID", "")
                    
                    model_data = {
                        "model_id": model_id,
                        "model_name": model_name,
                        "brand_name": item.get("Make_Name", brand_name)
                    }
                    
                    if year:
                        model_data["year"] = year
                    
                    models.append(model_data)
                
                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    models = [m for m in models if search_lower in m["model_name"].lower()]
                
                # Apply limit
                models = models[:limit]
                
                return {
                    "brand": brand_name,
                    "total_models": len(models),
                    "year": year if year else "All years",
                    "models": models
                }
            
            return {"brand": brand_name, "total_models": 0, "models": []}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


@router.get("/brands/{brand_name}/years")
async def get_years_by_brand(
    brand_name: str,
    model_name: Optional[str] = Query(None, description="Filter by specific model")
):
    """
    Get available years for a specific brand or brand-model combination
    
    Examples:
    - All years for Tesla: /brands/Tesla/years
    - Years for Tesla Model S: /brands/Tesla/years?model_name=Model S
    """
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            years_set = set()
            
            if model_name:
                # Get years for specific model
                url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetVehicleTypesForMakeId/year/make/{brand_name}/model/{model_name}?format=json"
            else:
                # Get all years for brand
                # Fetch recent years (2010-2025)
                for year in range(2025, 2009, -1):
                    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/{brand_name}/modelyear/{year}?format=json"
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("Results") and len(data["Results"]) > 0:
                        years_set.add(year)
            
            # If model_name is provided, use a different approach
            if model_name and not years_set:
                # Alternative endpoint for specific model years
                for year in range(2025, 2009, -1):
                    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetVehicleTypesForMakeId/year/make/{brand_name}/model/{model_name}/year/{year}?format=json"
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("Results") and len(data["Results"]) > 0:
                        years_set.add(year)
            
            years_list = sorted(list(years_set), reverse=True)
            
            return {
                "brand": brand_name,
                "model": model_name if model_name else "All models",
                "available_years": years_list,
                "total_years": len(years_list)
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch years: {str(e)}")


@router.get("/brands/{brand_name}/vehicles")
async def get_vehicles_by_brand(
    brand_name: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    model: Optional[str] = Query(None, description="Filter by model name"),
    include_fields: Optional[str] = Query(None, description="Comma-separated fields to include: brand, model, year, vehicle_type, body_class, manufacturer, full_name"),
    exclude_fields: Optional[str] = Query(None, description="Comma-separated fields to exclude"),
    limit: int = Query(50, description="Number of vehicles to return", ge=1, le=100)
):
    """
    Get detailed vehicle information by brand with filters
    Returns complete vehicle details similar to VIN lookup
    
    Examples:
    - All Tesla vehicles: /vehicles/brands/Tesla/vehicles
    - Tesla vehicles from 2022: /vehicles/brands/Tesla/vehicles?year=2022
    - Tesla Model S: /vehicles/brands/Tesla/vehicles?model=Model S
    - Tesla Model S 2022: /vehicles/brands/Tesla/vehicles?model=Model S&year=2022
    - Only brand and model: /vehicles/brands/Tesla/vehicles?include_fields=brand,model
    """
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            vehicles = []
            
            # First, get all models for the brand
            if year:
                url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/{brand_name}/modelyear/{year}?format=json"
            else:
                url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformake/{brand_name}?format=json"
            
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data.get("Results"):
                for item in data["Results"]:
                    model_name = item.get("Model_Name", "")
                    
                    # Apply model filter
                    if model and model.lower() not in model_name.lower():
                        continue
                    
                    # Fetch detailed vehicle information
                    detail_url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetVehicleTypesForMakeId/make/{brand_name}/model/{model_name}?format=json"
                    
                    try:
                        detail_response = await client.get(detail_url)
                        detail_response.raise_for_status()
                        detail_data = detail_response.json()
                        
                        vehicle_type = "N/A"
                        body_class = "N/A"
                        
                        if detail_data.get("Results") and len(detail_data["Results"]) > 0:
                            vehicle_type = detail_data["Results"][0].get("VehicleTypeName", "N/A")
                            body_class = detail_data["Results"][0].get("BodyClass", "N/A")
                        
                        # Build complete vehicle details
                        vehicle_info = {
                            "brand": brand_name.upper(),
                            "model": model_name,
                            "year": str(year) if year else "N/A",
                            "color": None,  # Color not available from API
                            "vehicle_type": vehicle_type.lower() if vehicle_type != "N/A" else "car",
                            "body_class": body_class if body_class != "N/A" else None,
                            "manufacturer": brand_name.upper(),
                            "full_name": f"{year} {brand_name.upper()} {model_name}" if year else f"{brand_name.upper()} {model_name}",
                            "message": "Color information is not available from this API. Please add manually."
                        }
                        
                        vehicles.append(vehicle_info)
                        
                    except Exception as e:
                        # If detail fetch fails, still add basic info
                        vehicle_info = {
                            "brand": brand_name.upper(),
                            "model": model_name,
                            "year": str(year) if year else "N/A",
                            "color": None,
                            "vehicle_type": "car",
                            "body_class": None,
                            "manufacturer": brand_name.upper(),
                            "full_name": f"{year} {brand_name.upper()} {model_name}" if year else f"{brand_name.upper()} {model_name}",
                            "message": "Limited information available"
                        }
                        vehicles.append(vehicle_info)
                    
                    if len(vehicles) >= limit:
                        break
            
            # Apply field filtering to each vehicle
            filtered_vehicles = []
            for vehicle in vehicles:
                if include_fields:
                    field_list = [f.strip() for f in include_fields.split(",")]
                    filtered_vehicle = {k: v for k, v in vehicle.items() if k in field_list}
                    filtered_vehicles.append(filtered_vehicle)
                elif exclude_fields:
                    exclude_list = [f.strip() for f in exclude_fields.split(",")]
                    filtered_vehicle = {k: v for k, v in vehicle.items() if k not in exclude_list}
                    filtered_vehicles.append(filtered_vehicle)
                else:
                    filtered_vehicles.append(vehicle)
            
            return {
                "brand": brand_name.upper(),
                "filters_applied": {
                    "year": year,
                    "model": model,
                    "include_fields": include_fields,
                    "exclude_fields": exclude_fields
                },
                "total_vehicles": len(filtered_vehicles),
                "vehicles": filtered_vehicles
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch vehicles: {str(e)}")

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