from fastapi.testclient import TestClient
import main

client = TestClient(main.app)
with client.stream('GET', '/api/stream') as response:
    print('status', response.status_code)
    print('ctype', response.headers.get('content-type', ''))
    first = next(response.iter_lines())
    print('first_line', first)

