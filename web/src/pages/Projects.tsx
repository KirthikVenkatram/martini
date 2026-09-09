import { useEffect, useState } from "react";
import { listProjects } from "../api";
import { Link } from "../components/Link";
import type { ProjectRecord } from "../types";
import NewProduction from "./NewProduction";

export default function Projects() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listProjects().then(setProjects);
  }, [creating]);

  return (
    <main className="min-h-screen bg-board px-6 py-8 text-paper">
      <div className="mx-auto max-w-3xl pb-6">
        <h1 className="font-narrow text-xl font-bold uppercase tracking-widest">Productions</h1>
      </div>

      {creating ? (
        <NewProduction onCancel={() => setCreating(false)} />
      ) : (
        <div className="mx-auto grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-3">
          <Link to="/day/14" className="block rounded-sm bg-paper p-3 text-ink">
            <p className="font-narrow text-sm font-bold">Invented Production</p>
            <p className="font-body text-xs text-ink/50">Sample production</p>
          </Link>
          {projects.map((project) => (
            <div key={project.slug} className="rounded-sm bg-paper p-3 text-ink">
              <p className="font-narrow text-sm font-bold">{project.title}</p>
              <p className="font-body text-xs text-ink/50">
                {project.total_days} days · crew {project.crew_size}
              </p>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex items-center justify-center rounded-sm border border-dashed border-paper/30 p-3 font-narrow text-sm font-bold uppercase text-paper/60"
          >
            + New production
          </button>
        </div>
      )}
    </main>
  );
}
