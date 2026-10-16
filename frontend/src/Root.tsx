import App from "./App";
import AgencyGate from "./AgencyGate";
import CustomerIntake from "./CustomerIntake";
import DemoSite from "./DemoSite";
import { Welcome } from "./Welcome";
import CustomerPortal from "./CustomerPortal";
export default function Root() {
  if (location.pathname === "/" || location.pathname === "") return <Welcome />;
  if (location.pathname === "/customer") return <CustomerPortal />;
  if (location.pathname === "/customer/signup")
    return <CustomerPortal mode="signup" />;
  if (location.pathname === "/customer/signin")
    return <CustomerPortal mode="signin" />;
  const match = location.pathname.match(
    /^\/(c|s|demo)\/([A-Za-z0-9_-]{43})\/?$/,
  );
  if (match) {
    if (match[1] === "demo") return <DemoSite token={match[2]} />;
    return (
      <CustomerIntake
        intakeToken={match[1] === "c" ? match[2] : undefined}
        resumeToken={match[1] === "s" ? match[2] : undefined}
      />
    );
  }
  if (/^\/(c|s|demo)\//.test(location.pathname))
    return (
      <div className="customer-unavailable">
        <h1>This feedback link is unavailable.</h1>
        <p>Ask the agency for a new project link.</p>
      </div>
    );
  if (location.pathname !== "/workspace") return <Welcome />;
  return (
    <AgencyGate>
      <App />
    </AgencyGate>
  );
}
