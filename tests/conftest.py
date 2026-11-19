import pytest
from app import create_app, db
@pytest.fixture
def app(tmp_path):
    database=tmp_path/'test.db'
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{database}','ENABLE_LIVE_SCRAPING':False})
    with app.app_context(): db.drop_all(); db.create_all()
    yield app
    with app.app_context(): db.session.remove(); db.drop_all()
@pytest.fixture
def client(app): return app.test_client()
