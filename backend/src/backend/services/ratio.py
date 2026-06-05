def get_working_capital_metrics(
    financials: HistoricalFinancials
) -> Dict[str, Dict[str, float | None]]:

    dates = [f.fiscal_year for f in financials.periods]

    receivables = [
        f.balance_sheet.accounts_receivable
        for f in financials.periods
    ]

    inventory = [
        f.balance_sheet.inventory
        for f in financials.periods
    ]

    payables = [
        f.balance_sheet.accounts_payable
        for f in financials.periods
    ]

    revenue = [
        f.income_statement.revenue
        for f in financials.periods
    ]

    cogs = [
        f.income_statement.cost_of_revenue
        for f in financials.periods
    ]

    dso_values = dso(
        receivables,
        revenue
    )

    dio_values = dio(
        inventory,
        cogs
    )

    dpo_values = dpo(
        payables,
        cogs
    )

    return {
        date: {
            "dso": dso_v,
            "dio": dio_v,
            "dpo": dpo_v,
        }
        for date, dso_v, dio_v, dpo_v in zip(
            dates,
            dso_values,
            dio_values,
            dpo_values
        )
    }