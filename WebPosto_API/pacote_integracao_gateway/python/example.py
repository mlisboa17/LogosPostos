import os
from pprint import pprint

from dotenv import load_dotenv

from gateway_client import GatewayConfig, LogosGatewayClient


def main() -> None:
    load_dotenv("../.env")

    config = GatewayConfig(
        base_url=os.getenv("LOGOS_GATEWAY_BASE_URL", "http://127.0.0.1:8050"),
        consumer_token=os.getenv("LOGOS_GATEWAY_CONSUMER_TOKEN", "<CONSUMER_TOKEN>"),
        posto_id=os.getenv("LOGOS_GATEWAY_POSTO_ID", "VIP"),
        timeout_seconds=int(os.getenv("LOGOS_GATEWAY_TIMEOUT_SECONDS", "15")),
    )

    client = LogosGatewayClient(config)

    print("== READY ==")
    pprint(client.ready())

    print("\n== HEALTH ==")
    pprint(client.health())

    print("\n== PRODUCTS ==")
    products = client.get_products(include_inactive=False, force_refresh=False)
    pprint({"posto_id": products.get("posto_id"), "total": products.get("total")})


if __name__ == "__main__":
    main()
