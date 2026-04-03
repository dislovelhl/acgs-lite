import { Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/DashboardPage";
import { RulesPage } from "@/pages/RulesPage";
import { RuleBuilderPage } from "@/pages/RuleBuilderPage";
import { PlaygroundPage } from "@/pages/PlaygroundPage";
import { AuditPage } from "@/pages/AuditPage";
import { RuleGraphPage } from "@/pages/RuleGraphPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="rules" element={<RulesPage />} />
        <Route path="builder" element={<RuleBuilderPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="graph" element={<RuleGraphPage />} />
      </Route>
    </Routes>
  );
}
