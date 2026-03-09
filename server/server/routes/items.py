from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.services.item_service import item_service

router = APIRouter(prefix="/items")


class CreateItemRequest(BaseModel):
    name: str
    description: str


@router.get("")
def list_items():
    return item_service.list()


@router.get("/{item_id}")
def get_item(item_id: str):
    item = item_service.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("", status_code=201)
def create_item(body: CreateItemRequest):
    return item_service.create(name=body.name, description=body.description)
