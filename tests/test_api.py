def test_health(client):
    response=client.get('/health')
    assert response.status_code==200
    assert response.json['status']=='ok'
def test_search_requires_query(client):
    response=client.post('/api/search',json={})
    assert response.status_code==400
def test_search_returns_partial_empty_result(client):
    response=client.post('/api/search',json={'query':'iPhone 17 Pro'})
    assert response.status_code==200
    assert response.json['results']==[]
def test_emi_endpoint(client):
    response=client.post('/api/emi',json={'price':120000,'down_payment':20000,'tenure':12,'interest_rate':0})
    assert response.status_code==200
    assert response.json['monthly_emi']==round(100000/12,2)
def test_invalid_emi(client):
    response=client.post('/api/emi',json={'price':1000,'down_payment':2000,'tenure':12})
    assert response.status_code==400
