from session import engine
from models import Base

print("Dropping existing tables...")
Base.metadata.drop_all(engine)

print("Creating tables...")
Base.metadata.create_all(engine)
print("Tables created.")