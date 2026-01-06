from pydantic import BaseModel, Field
from typing import List, Optional

class BoardingHouseSummary(BaseModel):# this one loads a detailed view when clicked on 
    name: str
    images: List[str]
    price_4: Optional[str]
    price_3: Optional[str]
    price_2: Optional[str]
    price_1: Optional[str]
    sharedroom_4: Optional[str]
    sharedroom_3: Optional[str]
    sharedroom_2: Optional[str]
    singleroom: Optional[str]
    amenities: List[str]
    location: Optional[str]

class BoardingHouseHomepage(BaseModel)   #this is where it will be sorting in the database to diplay

    name_boardinghouse: str # the boarding house name  
    price: str
    image:
    gender: str #the value that passes since there boolen values will come here and an icon will show
    rating: # based upon the number wil expand upon it later 

class BoardingHouse(BaseModel):
    name: str 
    location: str 
    university: str 
    landlord_id: str 
    price_4: str 
    price_3: str 
    price_2: str 
    price_1: str 
    GPS_coordinates: Optional[str] 
    yango_coordinates: Optional[str] 
    gender_male: Optional[bool] = False 
    gender_female: Optional[bool] = False 
    gender_both: Optional[bool] = False 
    sharedroom_4: str = Field(..., example="available")
    sharedroom_3: str = Field(..., example="unavailable")
    sharedroom_2: str = Field(..., example="not_supported")
    singleroom: str = Field(..., example="available")
    amenities: List[str]
    images: List[str] 
    rating: Optional[float] = None


#so BoardingHouse is the one that we will use for making a post for entering a boarding houses
#BoardingHouseHomepage is the one that wil display on home page so it will be a get request
# BoardingHouseSummary is the one that will display when a user clicks a boarding house on home page this endpoint with a get request will get more detail about the boarding house lets start with these endpoints
#and also when storing store them like landlord was stored insiden USERS with its own sub collecction called boardinghouses
#so if each boarding house gets entered and i enter CUZ it gets saved under CUZ if CBU gets saved under CBU folder in USERS
#when it comes to filtering i want it to be getting a request for the boarding house eg the request each time must be university/student_id/request get they should also move around in he server with the jwt token from securtity.py because some route will want you to be a premium memeber to enter 
#i want the university/sstudent_id/request to be there because i need to only allow those that are in my database to roam around so that user_id is like security reason if you come in with out an id you get kicked out and told to login or create an account 