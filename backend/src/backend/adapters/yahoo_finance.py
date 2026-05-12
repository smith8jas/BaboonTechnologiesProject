def main():
    ticker = "AAPL"
    price = get_stock_price(ticker)
    print(f"The current price of {ticker} is ${price}")


def get_stock_price(ticker):
    return 100


main()