import httpx
import json
import redis
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException
from datetime import datetime, timedelta
from functools import lru_cache
import asyncio

class VINDecoderService:
    """Production-ready VIN decoding service with caching"""
    
    BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"
    
    # Cache configuration
    CACHE_TTL = 86400  # 24 hours cache
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.local_cache = {}
    
    async def decode_vin(self, vin: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Decode VIN with caching for performance
        
        Args:
            vin: 17-character VIN number
            use_cache: Whether to use cached results
        
        Returns:
            Vehicle details dictionary
        """
        # Clean and validate VIN
        vin = vin.strip().upper()
        if len(vin) != 17:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid VIN length: {len(vin)}. VIN must be exactly 17 characters"
            )
        
        # Check cache first
        if use_cache:
            cached_result = await self._get_from_cache(vin)
            if cached_result:
                return cached_result
        
        # Fetch from API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Multiple API endpoints for reliability
                vehicle_info = await self._fetch_from_nhtsa(client, vin)
                
                if not vehicle_info.get("success"):
                    # Try alternative endpoint
                    vehicle_info = await self._fetch_from_nhtsa_alternative(client, vin)
                
                # Cache the result
                if vehicle_info.get("success"):
                    await self._save_to_cache(vin, vehicle_info)
                
                return vehicle_info
                
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"VIN decoding service unavailable: {str(e)}"
            )
    
    async def _fetch_from_nhtsa(self, client: httpx.AsyncClient, vin: str) -> Dict[str, Any]:
        """Fetch from primary NHTSA endpoint"""
        try:
            # Primary endpoint
            url = f"{self.BASE_URL}/DecodeVinValues/{vin}?format=json"
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("Results") and len(data["Results"]) > 0:
                result = data["Results"][0]
                
                # Check if VIN is valid
                error_code = result.get("ErrorCode", "0")
                if error_code != "0":
                    return {
                        "success": False,
                        "error": result.get("ErrorText", "Invalid VIN"),
                        "error_code": error_code
                    }
                
                # Extract and format vehicle information
                return self._format_vehicle_response(result, vin, success=True)
            
            return {
                "success": False,
                "error": "No vehicle data found for this VIN"
            }
            
        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"API request failed: {str(e)}"
            }
    
    async def _fetch_from_nhtsa_alternative(self, client: httpx.AsyncClient, vin: str) -> Dict[str, Any]:
        """Fallback to alternative NHTSA endpoint"""
        try:
            # Alternative endpoint with different parameters
            url = f"{self.BASE_URL}/DecodeVin/{vin}?format=json"
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("Results"):
                # Parse the extended results
                result = self._parse_alternative_response(data["Results"])
                return self._format_vehicle_response(result, vin, success=True)
            
            return {
                "success": False,
                "error": "VIN not found in alternative API"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Alternative API failed: {str(e)}"
            }
    
    def _parse_alternative_response(self, results: list) -> Dict[str, Any]:
        """Parse alternative API response format"""
        vehicle_data = {}
        for item in results:
            variable = item.get("Variable", "")
            value = item.get("Value", "")
            
            # Map variables to our format
            variable_lower = variable.lower()
            if "make" in variable_lower:
                vehicle_data["Make"] = value
            elif "model" in variable_lower:
                vehicle_data["Model"] = value
            elif "year" in variable_lower:
                vehicle_data["ModelYear"] = value
            elif "body class" in variable_lower:
                vehicle_data["BodyClass"] = value
            elif "vehicle type" in variable_lower:
                vehicle_data["VehicleType"] = value
            elif "manufacturer" in variable_lower:
                vehicle_data["Manufacturer"] = value
        
        return vehicle_data
    
    def _format_vehicle_response(self, data: Dict[str, Any], vin: str, success: bool) -> Dict[str, Any]:
        """Format API response to standard format"""
        
        if not success:
            return {
                "vin": vin,
                "success": False,
                "error": data.get("error", "Unknown error"),
                "brand": None,
                "model": None,
                "year": None,
                "vehicle_type": "car",
                "body_class": None,
                "manufacturer": None,
                "fuel_type": None,
                "engine_size": None,
                "drive_type": None
            }
        
        # Extract year safely
        year = data.get("ModelYear")
        if year and str(year).isdigit():
            year = int(year)
        else:
            year = None
        
        # Map vehicle type
        vehicle_type = self._map_vehicle_type(
            data.get("VehicleType", ""),
            data.get("BodyClass", "")
        )
        
        return {
            "vin": vin,
            "success": True,
            "brand": data.get("Make", "").strip(),
            "model": data.get("Model", "").strip(),
            "year": year,
            "vehicle_type": vehicle_type,
            "body_class": data.get("BodyClass", "").strip(),
            "manufacturer": data.get("Manufacturer", "").strip(),
            "fuel_type": data.get("FuelTypePrimary", "").strip(),
            "engine_cylinders": data.get("EngineCylinders"),
            "engine_size": data.get("DisplacementL", ""),
            "drive_type": data.get("DriveType", "").strip(),
            "transmission": data.get("TransmissionStyle", "").strip(),
            "plant_city": data.get("PlantCity", "").strip(),
            "plant_country": data.get("PlantCountry", "").strip(),
            "plant_state": data.get("PlantState", "").strip(),
            "trim": data.get("Trim", "").strip(),
            "series": data.get("Series", "").strip(),
            "gross_weight": data.get("GrossVehicleWeightRating", ""),
            "error_code": data.get("ErrorCode", "0"),
            "error_text": data.get("ErrorText", "")
        }
    
    def _map_vehicle_type(self, vehicle_type: str, body_class: str) -> str:
        """Map NHTSA vehicle types to standard categories"""
        vehicle_type_lower = vehicle_type.lower()
        body_class_lower = body_class.lower()
        
        # Comprehensive mapping for US vehicles
        mapping = {
            "motorcycle": ["motorcycle", "moped", "scooter"],
            "truck": ["truck", "pickup", "light truck"],
            "suv": ["suv", "sport utility", "crossover", "utility"],
            "van": ["van", "minivan", "passenger van", "cargo van"],
            "bus": ["bus", "school bus", "transit bus"],
            "trailer": ["trailer", "semi-trailer"],
            "car": ["passenger car", "sedan", "coupe", "hatchback", "convertible"]
        }
        
        for vehicle_category, keywords in mapping.items():
            for keyword in keywords:
                if keyword in vehicle_type_lower or keyword in body_class_lower:
                    return vehicle_category
        
        return "car"  # Default
    
    async def _get_from_cache(self, vin: str) -> Optional[Dict[str, Any]]:
        """Get cached VIN data"""
        # Check local memory cache first
        if vin in self.local_cache:
            cache_entry = self.local_cache[vin]
            if datetime.now() < cache_entry["expires"]:
                return cache_entry["data"]
        
        # Check Redis cache if available
        if self.redis_client:
            try:
                cached = self.redis_client.get(f"vin:{vin}")
                if cached:
                    data = json.loads(cached)
                    # Update local cache
                    self.local_cache[vin] = {
                        "data": data,
                        "expires": datetime.now() + timedelta(seconds=self.CACHE_TTL)
                    }
                    return data
            except Exception:
                pass
        
        return None
    
    async def _save_to_cache(self, vin: str, data: Dict[str, Any]):
        """Save VIN data to cache"""
        # Save to local cache
        self.local_cache[vin] = {
            "data": data,
            "expires": datetime.now() + timedelta(seconds=self.CACHE_TTL)
        }
        
        # Save to Redis if available
        if self.redis_client:
            try:
                self.redis_client.setex(
                    f"vin:{vin}",
                    self.CACHE_TTL,
                    json.dumps(data)
                )
            except Exception:
                pass
    
    async def batch_decode(self, vins: list[str]) -> Dict[str, Dict[str, Any]]:
        """Decode multiple VINs concurrently"""
        tasks = [self.decode_vin(vin) for vin in vins]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        result_dict = {}
        for vin, result in zip(vins, results):
            if isinstance(result, Exception):
                result_dict[vin] = {
                    "success": False,
                    "error": str(result)
                }
            else:
                result_dict[vin] = result
        
        return result_dict
    
    async def get_vehicle_by_vin_full(self, vin: str) -> Dict[str, Any]:
        """Get comprehensive vehicle details"""
        basic_info = await self.decode_vin(vin)
        
        if not basic_info["success"]:
            return basic_info
        
        # Add US-specific information
        return {
            **basic_info,
            "region_specific": {
                "market": "USA",
                "complies_with_us_regulations": True,
                "epa_class": self._get_epa_class(basic_info.get("gross_weight", "")),
                "us_dmv_category": self._get_dmv_category(basic_info.get("vehicle_type", ""))
            },
            "additional_details": {
                "is_electric": basic_info.get("fuel_type", "").lower() in ["electric", "battery electric"],
                "is_hybrid": "hybrid" in basic_info.get("fuel_type", "").lower(),
                "towing_capability": self._estimate_towing_capacity(basic_info)
            }
        }
    
    def _get_epa_class(self, gross_weight: str) -> str:
        """Get EPA vehicle class based on weight"""
        if not gross_weight:
            return "Unknown"
        
        try:
            weight = int(gross_weight)
            if weight < 6000:
                return "Light-Duty"
            elif weight < 10000:
                return "Medium-Duty"
            else:
                return "Heavy-Duty"
        except:
            return "Unknown"
    
    def _get_dmv_category(self, vehicle_type: str) -> str:
        """Get US DMV registration category"""
        categories = {
            "motorcycle": "Motorcycle",
            "truck": "Commercial Truck",
            "suv": "Passenger Vehicle",
            "van": "Passenger Van",
            "car": "Passenger Vehicle"
        }
        return categories.get(vehicle_type, "Passenger Vehicle")
    
    def _estimate_towing_capacity(self, vehicle_info: Dict[str, Any]) -> str:
        """Estimate towing capacity based on vehicle type"""
        vehicle_type = vehicle_info.get("vehicle_type", "")
        gross_weight = vehicle_info.get("gross_weight", "")
        
        if "truck" in vehicle_type:
            return "5,000 - 10,000 lbs"
        elif "suv" in vehicle_type:
            return "3,500 - 7,000 lbs"
        elif "van" in vehicle_type:
            return "3,000 - 6,000 lbs"
        else:
            return "Up to 2,000 lbs"


# Singleton instance
vin_decoder = VINDecoderService()