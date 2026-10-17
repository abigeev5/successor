import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useMe } from "@/api/auth";
import type { User, UserRole } from "@/api/client";
import { FullPageSpinner } from "@/components/Spinner";
import { AssistantPage } from "@/features/assistant/AssistantPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ConsentPage } from "@/features/consent/ConsentPage";
import { GapsPage } from "@/features/gaps/GapsPage";
import { HandoverPage } from "@/features/handovers/HandoverPage";
import { HandoversPage } from "@/features/handovers/HandoversPage";
import { InterviewPage } from "@/features/interview/InterviewPage";
import { KnowledgePage } from "@/features/knowledge/KnowledgePage";
import { ReviewPage } from "@/features/review/ReviewPage";
import { SectionPage } from "@/features/sections/SectionPage";
import { homePath } from "@/lib/roles";

import { Layout } from "./Layout";

const ALL: UserRole[] = ["admin", "manager", "expert", "successor"];

/** Pages by role (SPEC 9.1). Access to a specific handover is checked by the backend. */
const PAGES: { path: string; roles: UserRole[]; element: ReactNode }[] = [
  { path: "handovers", roles: ["admin", "manager", "expert"], element: <HandoversPage /> },
  { path: "handovers/:id", roles: ALL, element: <HandoverPage /> },
  { path: "consent/:handoverId", roles: ["expert"], element: <ConsentPage /> },
  { path: "interview/:sessionId", roles: ["expert", "admin"], element: <InterviewPage /> },
  { path: "review", roles: ["expert", "admin"], element: <ReviewPage /> },
  { path: "assistant", roles: ["successor", "manager"], element: <AssistantPage /> },
  { path: "knowledge", roles: ALL, element: <KnowledgePage /> },
  { path: "gaps", roles: ["manager", "expert", "admin"], element: <GapsPage /> },
  // Placeholders until their milestones (docs/plan.md).
  { path: "dashboard", roles: ["manager"], element: <SectionPage section="dashboard" /> },
  { path: "privacy", roles: ["expert"], element: <SectionPage section="privacy" /> },
  { path: "admin", roles: ["admin"], element: <SectionPage section="admin" /> },
];

function Protected() {
  const me = useMe();
  const location = useLocation();

  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) {
    return (
      <p role="alert" className="p-6 text-center text-sm text-danger">
        Сервер недоступен: {me.error.message}
      </p>
    );
  }
  if (!me.data)
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;

  const user: User = me.data;
  const home = <Navigate to={homePath(user.role)} replace />;
  return (
    <Routes>
      <Route element={<Layout user={user} />}>
        <Route index element={home} />
        {PAGES.map((page) => (
          <Route
            key={page.path}
            path={page.path}
            element={page.roles.includes(user.role) ? page.element : home}
          />
        ))}
        <Route path="*" element={home} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<Protected />} />
    </Routes>
  );
}
