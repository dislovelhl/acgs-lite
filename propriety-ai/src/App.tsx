import { Routes, Route } from "react-router-dom"
import { Nav } from "@/components/nav"
import { Footer } from "@/components/footer"
import Home from "./pages/Home"
import Assessment from "./pages/Assessment"
import Pricing from "./pages/Pricing"
import About from "./pages/About"
import Compliance from "./pages/Compliance"
import Privacy from "./pages/Privacy"
import Dashboard from "./pages/Dashboard"
import NotFound from "./pages/NotFound"

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/assessment" element={<Assessment />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<About />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <Footer />
    </>
  )
}
