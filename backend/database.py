from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Tes infos de connexion (les mêmes que dans ton Docker)
SQLALCHEMY_DATABASE_URL = "postgresql://jimmy_user:secure_password_123@localhost:5432/jimmy_nba_db"

# Création du moteur
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# La session pour faire les requêtes
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# La classe de base pour tes modèles
Base = declarative_base()

# Petite fonction utilitaire pour récupérer la BDD dans chaque route API
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()