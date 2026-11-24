from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    phone = State()


class Browse(StatesGroup):
    search_query = State()
    price_range = State()


class CartInput(StatesGroup):
    promo = State()


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address_choice = State()
    region = State()
    district = State()
    method = State()
    address = State()
    landmark = State()
    payment = State()
    confirm = State()
