from __future__ import annotations


def test_luxury_car_teach_me_how_to_buy_is_blocked():
    from icetea.safety import check

    v = check("can u teach me how to buy a lamborgini")
    assert v.blocked is True
    assert v.category == "out_of_scope"


def test_how_to_buy_lamborghini_blocked():
    from icetea.safety import check

    v = check("how to buy a Lamborghini")
    assert v.blocked is True
    assert v.category == "out_of_scope"


def test_how_to_buy_stock_not_blocked():
    from icetea.safety import check

    v = check("how to buy AAPL stock in a brokerage account")
    assert v.blocked is False


def test_coffee_machine_teach_me_how_to_buy_blocked_like_euser_journey():
    from icetea.safety import check

    v = check("can u teach me how to buy a coffee machine")
    assert v.blocked is True
    assert v.category == "out_of_scope"


def test_how_to_buy_house_not_blocked():
    from icetea.safety import check

    v = check("how to buy a house with a small down payment")
    assert v.blocked is False


def test_teach_me_how_to_buy_index_fund_not_blocked():
    from icetea.safety import check

    v = check("teach me how to buy an index fund in my IRA")
    assert v.blocked is False
