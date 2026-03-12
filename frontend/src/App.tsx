import { Routes, Route } from 'react-router-dom'
import { FilterProvider } from './context/FilterContext'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import ManageToZero from './pages/ManageToZero'
import WorkQueue from './pages/WorkQueue'
import Technicians from './pages/Technicians'
import TechnicianDetail from './pages/TechnicianDetail'
import BillingAudit from './pages/BillingAudit'

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
        </Route>
      </Routes>
    </FilterProvider>
  )
}
