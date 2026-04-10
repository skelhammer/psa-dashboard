import { Routes, Route } from 'react-router-dom'
import { FilterProvider } from './context/FilterContext'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import ManageToZero from './pages/ManageToZero'
import WorkQueue from './pages/WorkQueue'
import Technicians from './pages/Technicians'
import TechnicianDetail from './pages/TechnicianDetail'
import BillingAudit from './pages/BillingAudit'
import ClientHealth from './pages/ClientHealth'
import ClientDetail from './pages/ClientDetail'
import ExecutiveReport from './pages/ExecutiveReport'
import PhoneAnalytics from './pages/PhoneAnalytics'
import Contracts from './pages/Contracts'

export default function App() {
  return (
    <FilterProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/manage-to-zero" element={<ManageToZero />} />
          <Route path="/work-queue" element={<WorkQueue />} />
          <Route path="/technicians" element={<Technicians />} />
          <Route path="/technicians/:techId" element={<TechnicianDetail />} />
          <Route path="/billing" element={<BillingAudit />} />
          <Route path="/clients" element={<ClientHealth />} />
          <Route path="/clients/:clientId" element={<ClientDetail />} />
          <Route path="/executive" element={<ExecutiveReport />} />
          <Route path="/phone" element={<PhoneAnalytics />} />
          <Route path="/contracts" element={<Contracts />} />
        </Route>
      </Routes>
    </FilterProvider>
  )
}
