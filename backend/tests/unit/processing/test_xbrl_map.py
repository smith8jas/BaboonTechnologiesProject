from backend.processing.xbrl_map import XBRL_MAPPINGS

def test_xbrl_mappings_has_minimum_entries():
    assert len(XBRL_MAPPINGS) >= 30

def test_xbrl_mappings_covers_required_fields():
    required = {
        "revenue":           "Revenue",
        "gross_profit":      "GrossProfit",
        "operating_income":  "OperatingIncomeLoss",  # EBIT
        "net_income":        "NetIncome",
        "accounts_receivable":"TradeReceivables",
        "inventory":         "Inventories",
        "accounts_payable":  "TradePayables",
        "cash":              "CashAndMarketableSecurities",
        "ppe_net":           "PlantPropertyEquipmentNet",
        "total_equity":      "CommonEquity",
        "capex":             "CapitalExpenses",
        "da":                "DepreciationAmortizationCF",
    }
    for field, concept in required.items():
        assert field in XBRL_MAPPINGS, f"Missing field: {field}"
        assert XBRL_MAPPINGS[field] == concept, (
            f"{field} maps to '{XBRL_MAPPINGS[field]}', expected '{concept}'"
        )