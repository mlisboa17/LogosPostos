from datetime import datetime

from gateway_client import LogosGatewayClient


if __name__ == "__main__":
    client = LogosGatewayClient(
        base_url="http://127.0.0.1:8050",
        consumer_token="<CONSUMER_TOKEN>",
        timeout_seconds=10,
    )

    try:
        print("Health:", client.health())

        expenses = client.get_expenses(
            posto_id="23",
            data_consulta=datetime(2026, 5, 17, 0, 0, 0),
        )

        print(f"Posto: {expenses.posto_id}")
        print(f"Total de itens: {expenses.total}")
        for item in expenses.items:
            print(f"- {item.timestamp} | {item.descricao} | R$ {item.valor}")
    finally:
        client.close()

