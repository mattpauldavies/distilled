from app.domain.item import Item


class ItemService:
    def __init__(self) -> None:
        self._items: dict[str, Item] = {}

    def create(self, name: str, description: str) -> Item:
        item = Item(name=name, description=description)
        self._items[item.id] = item
        return item

    def list(self) -> list[Item]:
        return list(self._items.values())

    def get(self, item_id: str) -> Item | None:
        return self._items.get(item_id)


item_service = ItemService()
