/**
 * The add form Django admin's changelist always pairs with a list. One field: the
 * project's name. Submit is "save and continue editing" -- it lands on the new project's
 * own detail page, not back on the list, because the next thing a person does after
 * creating a project is add a review to it.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useCreateProject } from "@/api/queries";
import { useSession } from "@/app/session-context";

export function ProjectAddPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const navigate = useNavigate();

  const createProject = useCreateProject(slug);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const project = await createProject.mutateAsync({ name });
      await navigate({ to: "/projects/$projectUuid", params: { projectUuid: project.uuid } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("error.generic"));
    }
  }

  return (
    <main className="page">
      <form className="card" onSubmit={onSubmit}>
        <h1>{t("project.new")}</h1>

        <div className="field">
          <label htmlFor="project-name">{t("project.name")}</label>
          <input
            id="project-name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={createProject.isPending}>
          {t("project.create")}
        </button>
      </form>
    </main>
  );
}
