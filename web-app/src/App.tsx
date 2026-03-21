import { useState } from 'react'
import { Layout } from './components/Layout'
import { Dashboard } from './components/Dashboard'

function App() {
  const [isOnline, setIsOnline] = useState(false)

  return (
    <Layout isOnline={isOnline}>
      <Dashboard isOnline={isOnline} onHealthChange={setIsOnline} />
    </Layout>
  )
}

export default App
