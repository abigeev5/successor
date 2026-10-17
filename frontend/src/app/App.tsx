import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useMe } from "@/api/auth";
import type { User } from "@/api/client";
import { FullPageSpinner } from "@/components/Spinner";
import { LoginPage } from "@/features/auth/LoginPage";
import { SECTIONS, SectionPage } from "@/features/sections/SectionPage";
import { homePath, NAV } from "@/lib/roles";

import { Layout } from "./Layout";

function canOpen(user: User, path: string): boolean {
  return NAV[user.role].some((item) => item.to === path);
}

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
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  const user = me.data;
  return (
    <Routes>
      <Route element={<Layout user={user} />}>
        <Route index element={<Navigate to={homePath(user.role)} replace />} />
        {Object.keys(SECTIONS).map((section) => {
          const path = `/${section}`;
          return (
            <Route
              key={section}
              path={section}
              element={
                canOpen(user, path) ? (
                  <SectionPage section={section} />
                ) : (
                  <Navigate to={homePath(user.role)} replace />
                )
              }
            />
          );
        })}
        <Route path="*" element={<Navigate to={homePath(user.role)} replace />} />
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
