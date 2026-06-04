import asyncio
from datetime import datetime
import bcrypt
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

async def create_admin():
    client = AsyncIOMotorClient("mongodb+srv://vishnu:Vishnu123@developmentcluster.lu9ej3j.mongodb.net/")
    db = client["enzo_db"]
    
    # Hash password "Test@1234"
    pwd = b"Test@1234"
    salt = bcrypt.gensalt(10)
    hashed_pwd = bcrypt.hashpw(pwd, salt).decode('utf-8')
    print("Generated hash for Test@1234:", hashed_pwd)
    
    # Check if admin user already exists
    existing = await db.users.find_one({"email": "admin@enculture.ai"})
    
    admin_doc = {
        "email": "admin@enculture.ai",
        "userType": "Internal",
        "password": hashed_pwd,
        "role": [ObjectId("68b9a14f2d1b24d9ab534696")],
        "status": ObjectId("68c41ea07ec2670116e8e3ed"),
        "isDeleted": False,
        "isArchived": False,
        "basicDetails": {
            "profilePicUrl": "",
            "phoneNumber": "1234567890",
            "lastName": "Admin",
            "userId": "NHRT/ADMIN",
            "firstName": "Enculture",
            "emailId": "admin@enculture.ai",
            "userIdNormalized": "nhrt/admin",
            "azureAdObjectId": "admin-ad-object-id"
        },
        "demographicDetails": {
            "department": "Administration",
            "designation": "System Administrator",
            "gender": "Other",
            "location": "Corporate Headquarters"
        },
        "managerDetails": {
            "managerId": "NHRT/SYSTEM",
            "managerFirstName": "System",
            "managerEmailId": "system@enculture.ai",
            "managerLastName": "Root"
        },
        "showPrivacyPolicy": False,
        "showWelcomeMessage": False,
        "updatedAt": datetime.utcnow()
    }
    
    if existing:
        print("Admin user already exists. Updating password and details...")
        res = await db.users.update_one(
            {"email": "admin@enculture.ai"},
            {"$set": {
                "password": hashed_pwd,
                "basicDetails.firstName": "Enculture",
                "basicDetails.lastName": "Admin",
                "demographicDetails.department": "Administration",
                "demographicDetails.designation": "System Administrator",
                "demographicDetails.location": "Corporate Headquarters",
                "updatedAt": datetime.utcnow()
            }}
        )
        print("Matched count:", res.matched_count)
        print("Modified count:", res.modified_count)
    else:
        print("Creating new admin user...")
        admin_doc["createdAt"] = datetime.utcnow()
        res = await db.users.insert_one(admin_doc)
        print("Created admin user with ID:", res.inserted_id)

asyncio.run(create_admin())
