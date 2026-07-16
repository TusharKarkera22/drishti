// Merged Kannada string map: key -> Kannada text. English lives inline at each
// call site via t("key", "English"), so a missing key safely renders English.
// Each surface contributes one `*.kn.ts` module; add its import + spread here as
// the surface is wired for translation.
import { navKn } from "./nav.kn";
import { homeKn } from "./home.kn";
import { insightsKn } from "./insights.kn";
import { dashboardKn } from "./dashboard.kn";
import { mapKn } from "./map.kn";
import { agentsKn } from "./agents.kn";
import { networkKn } from "./network.kn";
import { intakeKn } from "./intake.kn";
import { reportKn } from "./report.kn";
import { dataKn } from "./data.kn";
import { commonKn } from "./common.kn";

export const KN: Record<string, string> = {
  ...navKn,
  ...homeKn,
  ...insightsKn,
  ...dashboardKn,
  ...mapKn,
  ...agentsKn,
  ...networkKn,
  ...intakeKn,
  ...reportKn,
  ...dataKn,
  ...commonKn,
};
