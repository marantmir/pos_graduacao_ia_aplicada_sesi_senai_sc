import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import Header from "./components/Header.jsx";
import LoadingState from "./components/LoadingState.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Login from "./pages/Login.jsx";
import { TeamSelectionProvider, useTeamSelection } from "./context/TeamSelectionContext.jsx";

const Admin = lazy(() => import("./pages/Admin.jsx"));
const CoachInsights = lazy(() => import("./pages/CoachInsights.jsx"));
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const FinalReport = lazy(() => import("./pages/FinalReport.jsx"));
const Formations = lazy(() => import("./pages/Formations.jsx"));
const FutureAI = lazy(() => import("./pages/FutureAI.jsx"));
const GamePlan = lazy(() => import("./pages/GamePlan.jsx"));
const History = lazy(() => import("./pages/History.jsx"));
const Matchup = lazy(() => import("./pages/Matchup.jsx"));
const NewAnalysis = lazy(() => import("./pages/NewAnalysis.jsx"));
const SourcesVideos = lazy(() => import("./pages/SourcesVideos.jsx"));
const SquadAnalysis = lazy(() => import("./pages/SquadAnalysis.jsx"));
const TacticalDossier = lazy(() => import("./pages/TacticalDossier.jsx"));
const TeamSearch = lazy(() => import("./pages/TeamSearch.jsx"));
const VideoAnalysis = lazy(() => import("./pages/VideoAnalysis.jsx"));

export default function App() {
  return (
    <TeamSelectionProvider>
      <Gate />
    </TeamSelectionProvider>
  );
}

function Gate() {
  const { onboarded, onboardingLoading } = useTeamSelection();

  if (onboardingLoading) return <LoadingState />;
  if (!onboarded) return <Login />;

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace">
        <Header />
        <main className="content">
          <Suspense fallback={<LoadingState />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/new-analysis" element={<NewAnalysis />} />
              <Route path="/search" element={<TeamSearch />} />
              <Route path="/video-analysis" element={<VideoAnalysis />} />
              <Route path="/coach-insights" element={<CoachInsights />} />
              <Route path="/team/:teamId" element={<TacticalDossier />} />
              <Route path="/team/:teamId/formations" element={<Formations />} />
              <Route path="/team/:teamId/squad" element={<SquadAnalysis />} />
              <Route path="/team/:teamId/sources" element={<SourcesVideos />} />
              <Route path="/team/:teamId/game-plan" element={<GamePlan />} />
              <Route path="/team/:teamId/report" element={<FinalReport />} />
              <Route path="/team/:teamId/matchup" element={<Matchup />} />
              <Route path="/history" element={<History />} />
              <Route path="/future-ai" element={<FutureAI />} />
              <Route path="/admin" element={<Admin />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
