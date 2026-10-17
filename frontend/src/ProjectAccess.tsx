import { useEffect, useState } from "react";
import { api, type Project } from "./types";
type Member = {
  id: string;
  name: string;
  email: string;
  revoked_at?: string | null;
};
type Access = {
  customer_access: "link" | "members";
  employees: Member[];
  customers: Member[];
};
export default function ProjectAccess() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState("");
  const [access, setAccess] = useState<Access | null>(null);
  const [role, setRole] = useState("employee");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Project[]>("/projects")
      .then((values) => {
        setProjects(values);
        setProject(values[0]?.id || "");
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setAccess(null);
    if (!project) return;
    let active = true;
    api<Access>(`/projects/${project}/access`)
      .then((value) => {
        if (active) setAccess(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project]);
  async function change(path: string, method: string, body?: unknown) {
    setBusy(true);
    setError("");
    try {
      setAccess(await api<Access>(`/projects/${project}` + path, method, body));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="conversation-card" aria-label="Project access">
      <span className="eyebrow">THE RIGHT PEOPLE, THE RIGHT PROJECT</span>
      <h2>Project access</h2>
      <p>
        Owners can access every project. Employees see only their assigned
        projects. Customer membership never gives access to another customer’s
        reports.
      </p>
      {!projects.length && (
        <p>Create a project in the workspace to manage its access.</p>
      )}
      {!!projects.length && (
        <label>
          Manage project
          <select
            aria-label="Manage project"
            value={project}
            disabled={busy}
            onChange={(e) => {
              setError("");
              setProject(e.target.value);
            }}
          >
            {projects.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {access && (
        <>
          <label className="project-access-mode">
            Customer submissions
            <select
              aria-label="Customer submissions"
              value={access.customer_access}
              disabled={busy}
              onChange={(e) =>
                void change("/access", "PATCH", { mode: e.target.value })
              }
            >
              <option value="link">Anyone with the project link</option>
              <option value="members">Invited customer accounts only</option>
            </select>
          </label>
          <p>
            {access.customer_access === "members"
              ? "Customers must sign in and be added below before opening this project or submitting a report. Guest access is blocked."
              : "The project link allows new customer reports and customer accounts to join. Removing a customer blocks that account from rejoining with the same link."}
          </p>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              await change(`/members/${role}`, "POST", { email });
              setEmail("");
            }}
          >
            <div className="project-member-fields">
              <label>
                Account type
                <select
                  aria-label="Account type"
                  value={role}
                  disabled={busy}
                  onChange={(e) => setRole(e.target.value)}
                >
                  <option value="employee">Employee</option>
                  <option value="customer">Customer</option>
                </select>
              </label>
              <label>
                Member email
                <input
                  required
                  type="email"
                  maxLength={254}
                  value={email}
                  disabled={busy}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            </div>
            <small>
              The person needs an existing account for the selected role. Create
              an employee invitation above for a new teammate.
            </small>
            <button className="primary-button" disabled={busy}>
              Add to project
            </button>
          </form>
          {(["employees", "customers"] as const).map((group) => (
            <div key={group} className="project-members">
              <h3>
                {group === "employees"
                  ? "Assigned employees"
                  : "Customer members"}
              </h3>
              {!access[group].length && <p>No {group} added yet.</p>}
              {access[group].map((member) => (
                <article className="team-member" key={member.id}>
                  <div>
                    <strong>{member.name}</strong>
                    <p>{member.email}</p>
                    {member.revoked_at && <small>Access removed</small>}
                  </div>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => {
                      if (member.revoked_at)
                        void change("/members/customer", "POST", {
                          email: member.email,
                        });
                      else if (
                        window.confirm(
                          `Remove ${member.name} from this project? They will lose access to its reports and notifications.`,
                        )
                      )
                        void change(
                          `/members/${group === "employees" ? "employee" : "customer"}/${member.id}`,
                          "DELETE",
                        );
                    }}
                  >
                    {member.revoked_at
                      ? "Restore project access"
                      : "Remove from project"}
                  </button>
                </article>
              ))}
            </div>
          ))}
        </>
      )}
    </section>
  );
}
