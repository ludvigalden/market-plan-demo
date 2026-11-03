import { Link, Route, Routes } from "react-router-dom";
import { CampaignPage } from "./pages/CampaignPage";
import { CampaignsPage } from "./pages/CampaignsPage";

export function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <Link to="/" className="brand">
          Market Plan Desk
        </Link>
        <span className="tagline">Demo Brand · fictional data</span>
      </header>
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<CampaignsPage />} />
          <Route path="/campaigns/:id" element={<CampaignPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
