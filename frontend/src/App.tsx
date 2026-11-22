import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import ChatWorkspace from './components/ChatWorkspace'
import Sidebar from './components/Sidebar'
import SystemStatusPage from './components/SystemStatus'

export default function App() {
  const [conversationKey, setConversationKey] = useState(0)
  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar onNewConversation={() => setConversationKey((key) => key + 1)} />
      <div className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<ChatWorkspace key={conversationKey} />} />
          <Route path="/status" element={<SystemStatusPage />} />
        </Routes>
      </div>
    </div>
  )
}
