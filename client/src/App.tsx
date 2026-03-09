import { useEffect, useState } from 'react'

interface Item {
  id: string
  name: string
  description: string
}

export default function App() {
  const [items, setItems] = useState<Item[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const fetchItems = async () => {
    const res = await fetch('/api/items')
    setItems(await res.json())
  }

  useEffect(() => {
    fetchItems()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await fetch('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    })
    setName('')
    setDescription('')
    fetchItems()
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-2xl font-bold">Items</h1>

      <form onSubmit={handleSubmit} className="mb-8 flex flex-col gap-3">
        <input
          className="rounded-md border border-border bg-background px-3 py-2"
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="rounded-md border border-border bg-background px-3 py-2"
          placeholder="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />
        <button
          type="submit"
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground hover:opacity-90"
        >
          Add Item
        </button>
      </form>

      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold">{item.name}</h2>
            <p className="text-sm text-muted-foreground">{item.description}</p>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-muted-foreground">No items yet. Add one above!</p>
        )}
      </div>
    </div>
  )
}
