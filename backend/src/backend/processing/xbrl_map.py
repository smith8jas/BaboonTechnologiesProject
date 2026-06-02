PS_MAPPINGS = {
    # ── Per Share ─────────────────────────────────────────────
    "eps_basic":                        "EarningsPerShareBasic",
    "eps_diluted":                      "EarningsPerShareDiluted",
    "basic_shares":                     "SharesAverage",
    "diluted_shares":                   "SharesFullyDilutedAverage",
    "shares_issued":                    "SharesIssued",
    "shares_year_end":                  "SharesYearEnd",
    "shares_dilution_adjustment":       "SharesDilutionAdjustment",
    "book_value_per_share":             "BookValuePerShare",
    "common_dividends_per_share":       "CommonDividendsPerShare",
}


IS_MAPPINGS = {

    # ── Revenue ───────────────────────────────────────────────
    "revenue":                          "Revenue",

    # ── Cost of Revenue ───────────────────────────────────────
    "cogs":                             "CostOfGoodsAndServicesSold",
    "gross_profit":                     "GrossProfit",

    # ── Operating Expenses ────────────────────────────────────
    "rd_expense":                       "ResearchAndDevelopmentExpenses",
    "sga_expense":                      "SellingGeneralAndAdminExpenses",
    "marketing_expense":                "MarketingExpenses",
    "depreciation_expense":             "DepreciationExpense",
    "amortization_intangibles":         "AmortizationOfIntangibles",
    "restructuring_expense":            "RestructuringExpenseBenefit",
    "goodwill_impairment":              "GoodwillWriteoffs",
    "other_operating_expense":          "OtherOperatingExpense",
    "total_opex":                       "TotalOperatingExpenses",
    "costs_subtotal":                   "CostsSubtotal",
    "bad_debt_expense":                 "BadDebtExpense",
    "labor_expenses":                   "LaborExpenses",
    "occupancy_expense":                "OccupancyExpense",
    "communication_tech_expense":       "CommunicationAndTechnologyExpense",
    "professional_fees":                "ProfessionalFees",
    "advertising_expense":              "AdvertisingExpense",
    "finance_lease_expense":            "FinanceLeaseExpense",
    "operating_lease_expense":          "OperatingLeaseExpense",
    "pension_expense":                  "PensionExpense",
    "asset_impairment":                 "AssetImpairmentChargesIS",
    "sbc_expense":                      "StockBasedCompensationExpense",

    # ── Operating Income ──────────────────────────────────────
    "ebit":                             "OperatingIncomeLoss",

    # ── Non-Operating Items ───────────────────────────────────
    "interest_expense":                 "InterestExpense",
    "interest_income":                  "InterestIncome",
    "interest_and_dividend_income":     "InterestAndDividendIncome",
    "nonoperating_income":              "NonoperatingIncomeExpense",
    "gain_loss_dispositions":           "GainLossOnDispositions",
    "gain_loss_investments":            "GainLossOnInvestmentsIS",
    "foreign_currency_gain_loss":       "ForeignCurrencyGainLoss",
    "equity_method_income":             "EquityMethodInvestmentIncome",
    "loss_debt_extinguishment":         "LossOnDebtExtinguishment",
    "other_income":                     "OtherIncomeIS",
    "other_expense":                    "OtherExpenseIS",

    # ── Pre-Tax & Tax ─────────────────────────────────────────
    "pretax_income":                    "PretaxIncomeLoss",
    "tax_expense":                      "IncomeTaxes",
    "current_tax_expense":              "CurrentIncomeTaxExpense",
    "deferred_tax_expense":             "DeferredIncomeTaxExpense",
    "valuation_allowance_dta":          "ValuationAllowanceDTA",

    # ── Net Income ────────────────────────────────────────────
    # Priority: NetIncome (common) → NetIncomeLoss → ProfitLoss (includes NCI)
    "net_income":                       ["ProfitLoss", "NetIncomeLoss", "NetIncome"],
    "net_income_to_common":             "NetIncomeToCommonShareholders",
    "minority_interest_income":         "MinorityInterestIncomeExpense",
    "income_continuing_operations":     "IncomeLossContinuingOperations",
    "discontinued_operations":          "DiscontinuedOperationsIncome",
    "extraordinary_items":              "ExtraordinaryItemsIncomeExpense(PostTax)",
    "special_items":                    "SpecialItemsIncomeExpense(Pretax)",
    "preferred_dividend_expense":       "PreferredDividendExpense",

    # ── Banking ───────────────────────────────────────────────
    "net_interest_income":              "NetInterestIncome",
    "net_interest_income_after_prov":   "NetInterestIncomeAfterProvision",
    "non_interest_income":              "NonInterestIncome",
    "total_interest_income_operating":  "TotalInterestIncomeOperating",
    "non_interest_expense":             "NonInterestExpense",
    "provision_credit_losses":          "ProvisionForCreditLosses",
    "interest_expense_deposits":        "InterestExpenseDeposits",

    # ── Insurance ─────────────────────────────────────────────
    "policy_benefits_claims":           "PolicyBenefitsAndClaims",

    # ── Comprehensive Income ──────────────────────────────────
    "comprehensive_income_net":         "ComprehensiveIncomeNet",
    "foreign_currency_translation":     "ForeignCurrencyTranslation",
    "unrealized_gains_losses_sec":      "UnrealizedGainsLossesSecurities",
    "pension_retirement_adjustments":   "PensionAndRetirementAdjustments",
    "hedging_gains_losses":             "HedgingGainsLosses",
    "aoci_reclassifications":           "AOCIReclassifications",
    "other_comprehensive_income":       "OtherComprehensiveIncomeLoss",
}


BS_MAPPINGS = {

    # ── Current Assets ────────────────────────────────────────
    "cash":                             "CashAndMarketableSecurities",
    "cash_and_equivalents":             "CashAndCashEquivalents",
    "restricted_cash_current":          "RestrictedCashCurrent",
    "short_term_investments":           "ShortTermInvestments",
    "accounts_receivable":              "TradeReceivables",
    "accounts_receivable_gross":        "AccountsReceivableGross",
    "allowance_doubtful":               "AllowanceForDoubtfulAccounts",
    "inventory":                        "Inventories",
    "prepaid_expenses":                 "PrepaidExpenses",
    "contract_assets":                  "ContractAssets",
    "income_tax_receivable":            "IncomeTaxReceivable",
    "deferred_tax_current_assets":      "DeferredTaxCurrentAssets",
    "customer_advances":                "CustomerAdvances",
    "assets_held_for_sale":             "AssetsHeldForSale",
    "other_current_assets":             "OtherOperatingCurrentAssets",
    "other_noncurrent_assets_current":  "OtherNonOperatingCurrentAssets",
    "other_noncurrent_assets_nc":       "OtherNonOperatingNonCurrentAssets",
    "retirement_related_current_assets":"RetirementRelatedCurrentAssets",
    "total_current_assets":             "CurrentAssetsTotal",

    # ── Non-Current Assets ────────────────────────────────────
    "ppe_gross":                        "GrossPropertyPlantEquipment",
    "ppe_net":                          "PlantPropertyEquipmentNet",
    "accumulated_depreciation":         "AccumulatedDepreciation",
    "goodwill":                         "Goodwill",
    "intangible_assets":                "IntangibleAssets",
    "intangible_assets_gross":          "IntangibleAssetsGross",
    "accumulated_amort_intangibles":    "AccumulatedAmortizationIntangibles",
    "goodwill_and_intangibles":         "GoodwillAndIntangiblesNet",
    "longterm_investments":             "LongtermInvestments",
    "equity_method_investments":        "InvestmentsEquityMethod",
    "operating_lease_rou_asset":        "OperatingLeaseRightOfUseAsset",
    "deferred_tax_noncurrent_assets":   "DeferredTaxNoncurrentAssets",
    "restricted_cash_noncurrent":       "RestrictedCashNonCurrent",
    "deferred_policy_acquisition":      "DeferredPolicyAcquisitionCosts",
    "security_deposits":                "SecurityDepositsAsset",
    "defined_benefit_plan_assets":      "DefinedBenefitPlanAssets",
    "real_estate_investments":          "RealEstateInvestments",
    "regulated_assets":                 "RegulatedAssets",
    "net_loans_and_leases":             "NetLoansAndLeases",
    "notes_receivable_noncurrent":      "NotesReceivableNonCurrent",
    "loan_loss_reserve":                "LoanLossReserve",
    "retirement_related_noncurrent_assets": "RetirementRelatedNonCurrentAssets",
    "other_noncurrent_assets":          "OtherOperatingNonCurrentAssets",
    "total_noncurrent_assets":          "NonCurrentAssetsTotal",
    "total_assets":                     "Assets",

    # ── Current Liabilities ───────────────────────────────────
    "accounts_payable":                 "TradePayables",
    "short_term_debt":                  "ShortTermDebt",
    "current_portion_ltd":              "CurrentPortionOfLongTermDebt",
    "operating_lease_current":          "OperatingLeaseCurrentDebtEquivalent",
    "deferred_revenue_current":         "DeferredRevenueCurrent",
    "contract_liabilities":             "ContractLiabilities",
    "taxes_payable":                    "TaxesPayable",
    "accrued_compensation":             "AccruedCompensation",
    "accrued_income_taxes":             "AccruedIncomeTaxes",
    "dividends_payable":                "DividendsPayable",
    "self_insurance_reserve":           "SelfInsuranceReserve",
    "deferred_tax_current_liab":        "DeferredTaxCurrentLiabilities",
    "ongoing_operating_provisions":     "OngoingOperatingProvisions(WarrantiesEtc)",
    "retirement_related_current_liab":  "RetirementRelatedCurrentLiabilities",
    "retirement_related_noncurrent_liab":"RetirementRelatedNonCurrentLiabilities",
    "other_noncurrent_current_liab":    "OtherNonOperatingCurrentLiabilities",
    "other_current_liabilities":        "OtherOperatingCurrentLiabilities",
    "total_current_liabilities":        "CurrentLiabilitiesTotal",

    # ── Non-Current Liabilities ───────────────────────────────
    "long_term_debt":                   "LongTermDebt",
    "convertible_debt":                 "ConvertibleDebtNonCurrent",
    "deferred_revenue_noncurrent":      "DeferredRevenueNonCurrent",
    "operating_lease_lt":               "OperatingLeaseNonCurrentDebtEquivalent",
    "deferred_tax_noncurrent_liab":     "DeferredTaxNonCurrentLiabilities",
    "pension_obligations":              "PensionObligations",
    "defined_benefit_obligations":      "DefinedBenefitPlanObligations",
    "deferred_compensation_noncurrent": "DeferredCompensationNonCurrent",
    "regulated_liabilities":            "RegulatedLiabilities",
    "total_deposits":                   "TotalDeposits",
    "asset_retirement_obligations":     "AssetRetirementObligations",
    "restructuring_provisions":         "RestructuringProvisions",
    "definite_lived_provisions":        "DefiniteLivedOperatingProvisions(DecommissioningEtc)",
    "other_noncurrent_liab_nonop":      "OtherNonOperatingNonCurrentLiabilities",
    "other_noncurrent_liabilities":     "OtherOperatingNonCurrentLiabilities",
    "total_noncurrent_liabilities":     "NonCurrentLiabilitiesTotal",
    "total_liabilities":                "Liabilities",

    # ── Equity ────────────────────────────────────────────────
    "common_equity":                    "CommonEquity",
    "total_equity":                     "AllEquityBalance",
    "total_equity_incl_minority":       "AllEquityBalanceIncludingMinorityInterest",
    "minority_interest_bs":             "MinorityInterestBS",
    "minority_interest_balance":        "MinorityInterestBalance",
    "preferred_stock":                  "PreferredStock",
    "additional_paid_in_capital":       "AdditionalPaidInCapital",
    "retained_earnings":                "RetainedEarnings",
    "accumulated_oci":                  "AccumulatedOtherComprehensiveIncome",
    "treasury_shares":                  "TreasuryShares",
    "temporary_mezzanine_financing":    "TemporaryAndMezzanineFinancing",
    "unearned_revenue_equity":          "UnearnedRevenue",
    "total_liabilities_and_equity":     "LiabilitiesAndEquity",

    # ── Statement of Equity ───────────────────────────────────
    "dividends_equity":                 "DividendsEquity",
    "stock_repurchases_equity":         "StockRepurchasesEquity",
    "stock_issuances_equity":           "StockIssuancesEquity",
    "stock_comp_equity_impact":         "StockCompensationEquityImpact",
}


CFS_MAPPINGS = {

    # ── Operating ─────────────────────────────────────────────
    "cfo":                              "NetCashFromOperatingActivities",
    # Priority: ProfitLoss (CFS start line) → NetIncomeLoss → NetIncome
    "net_income":                       ["ProfitLoss", "NetIncomeLoss", "NetIncome"],
    # Priority: expanded to catch TSLA and similar filers
    "depreciation_amortization":        [
                                            "DepreciationExpense",
                                            "DepreciationAndAmortization",
                                            "DepreciationDepletionAndAmortization",
                                        ],
    "sbc":                              "StockBasedCompensationCF",
    "deferred_tax_cf":                  "DeferredIncomeTaxCF",
    "change_in_receivables":            "ChangeInReceivables",
    "change_in_inventory":              "ChangeInInventory",
    "change_in_payables":               "ChangeInPayables",
    "change_in_deferred_revenue":       "ChangeInDeferredRevenue",
    "change_in_other_wc":               "ChangeInOtherWorkingCapital",
    "change_in_accrued_liab":           "ChangeInAccruedLiabilities",
    "provision_doubtful_cf":            "ProvisionForDoubtfulAccountsCF",
    "gain_loss_asset_sales_cf":         "GainLossOnAssetSalesCF",
    "impairment_charges_cf":            "ImpairmentChargesCF",
    "operating_lease_payments":         "OperatingLeasePayments",
    "finance_lease_payments":           "FinanceLeasePayments",
    "capital_lease_payments_cf":        "CapitalLeasePaymentsCF",
    "other_noncash_cf":                 "OtherNonCashItemsCF",

    # ── Investing ─────────────────────────────────────────────
    "capex":                            "CapitalExpenses",
    "investment_purchases":             "InvestmentPurchases",
    "investment_proceeds":              "InvestmentProceeds",
    "acquisitions_net":                 "AcquisitionsNet",
    "purchase_intangibles":             "PurchaseOfIntangibleAssets",
    "proceeds_sale_ppe":                "ProceedsFromSaleOfPPE",
    "proceeds_maturities_invest":       "ProceedsFromMaturitiesOfInvestments",
    "divestiture_proceeds":             "DivestitureProceeds",
    "net_cash_investing":               "NetCashFromInvestingActivities",

    # ── Financing ─────────────────────────────────────────────
    "debt_proceeds":                    "DebtProceeds",
    "debt_repayments":                  "DebtRepayments",
    "stock_repurchase_payments":        "StockRepurchasePayments",
    "stock_issuance_proceeds":          "StockIssuanceProceeds",
    "equity_expense_income":            "EquityExpenseIncome(BuybackIssued)",
    "dividends_paid":                   "CommonDividendsPaid",
    "distributions_minority":           "DistributionsToMinorityInterests",
    "debt_issuance_costs":              "PaymentsOfDebtIssuanceCosts",
    "fx_effect_on_cash":                "ForeignExchangeEffectOnCash",
    "net_cash_financing":               "NetCashFromFinancingActivities",

    # ── Summary ───────────────────────────────────────────────
    "net_change_in_cash":               "NetChangeInCash",

    # ── Commitments — Operating Lease ────────────────────────
    "op_lease_commitment_y1":           "OperatingLeaseCommitmentYear1",
    "op_lease_commitment_y2":           "OperatingLeaseCommitmentYear2",
    "op_lease_commitment_y3":           "OperatingLeaseCommitmentYear3",
    "op_lease_commitment_y4":           "OperatingLeaseCommitmentYear4",
    "op_lease_commitment_y5":           "OperatingLeaseCommitmentYear5",
    "op_lease_commitment_thereafter":   "OperatingLeaseCommitmentAfterYear5",

    # ── Commitments — Intangible Amortization Forecast ───────
    "intang_amort_forecast_y1":         "ForecastedIntangibleAmortizationYear1",
    "intang_amort_forecast_y2":         "ForecastedIntangibleAmortizationYear2",
    "intang_amort_forecast_y3":         "ForecastedIntangibleAmortizationYear3",
    "intang_amort_forecast_y4":         "ForecastedIntangibleAmortizationYear4",
    "intang_amort_forecast_y5":         "ForecastedIntangibleAmortizationYear5",
    "intang_amort_forecast_thereafter": "ForecastedIntangibleAmortizationAfterYear5",
}


def map_keys(row: dict, mappings: dict) -> dict:
    reverse: dict[str, str] = {}
    for internal, concept in mappings.items():
        for c in (concept if isinstance(concept, list) else [concept]):
            reverse[c] = internal

    out: dict = {}
    for internal in set(reverse.values()):
        candidates = [c for c, k in reverse.items() if k == internal]
        for c in candidates:
            if row.get(c) is not None:
                out[internal] = row[c]
                break
    return out


def map_all_periods(by_period: dict, mappings: dict) -> dict:
    return {period: map_keys(row, mappings) for period, row in by_period.items()}