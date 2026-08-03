from db.session import engine
from db.base import Base

print("Dropping existing tables...")
Base.metadata.drop_all(bind=engine)

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created.")