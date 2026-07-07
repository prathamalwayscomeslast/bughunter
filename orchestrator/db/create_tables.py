from session import engine
from models import Base

Base.metadata.create_all(engine)
print("Tables created.")