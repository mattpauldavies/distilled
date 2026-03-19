import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InfoButton } from './InfoButton'

describe('InfoButton', () => {
  it('does not show content before clicking', () => {
    render(<InfoButton content="Explanation text" />)
    expect(screen.queryByText('Explanation text')).not.toBeInTheDocument()
  })

  it('shows content after clicking the trigger', async () => {
    const user = userEvent.setup()
    render(<InfoButton content="Explanation text" />)
    await user.click(screen.getByRole('button', { name: /more information/i }))
    expect(screen.getByText('Explanation text')).toBeInTheDocument()
  })

  it('closes after clicking trigger again', async () => {
    const user = userEvent.setup()
    render(<InfoButton content="Explanation text" />)
    await user.click(screen.getByRole('button', { name: /more information/i }))
    await user.click(screen.getByRole('button', { name: /more information/i }))
    expect(screen.queryByText('Explanation text')).not.toBeInTheDocument()
  })
})
