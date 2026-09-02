/**
 * A finished report.
 *
 * The summary leads with three counts, never two. A specification that established
 * nothing says so in words, because a row with zeroes in it reads like a clean pass.
 */

import { useTranslation } from "react-i18next";

import type { Report } from "@/api/types";
import { StatusPill } from "@/components/StatusPill";

export function ReportView({ report }: { report: Report }) {
  const { t } = useTranslation();

  return (
    <section className="report">
      <header className="report__header">
        <div>
          <h3>{report.ids_title || report.ifc_filename}</h3>
          <p className="muted">
            {report.ifc_filename} · {t("report.schema", { schema: report.ifc_schema })} ·{" "}
            {t("report.engine", { version: report.engine_version })}
          </p>
        </div>
        <StatusPill status={report.status} />
      </header>

      <div className="counts">
        <div className="count count--pass">
          <span className="count__value">{report.passed}</span>
          <span className="count__label">{t("report.passed")}</span>
        </div>
        <div className="count count--fail">
          <span className="count__value">{report.failed}</span>
          <span className="count__label">{t("report.failed")}</span>
        </div>
        <div className="count count--indeterminate">
          <span className="count__value">{report.indeterminate}</span>
          <span className="count__label">{t("report.indeterminate")}</span>
        </div>
      </div>
      {report.indeterminate > 0 && (
        <p className="notice">{t("report.indeterminateNote")}</p>
      )}

      <h4>{t("report.specifications")}</h4>
      <ul className="specs">
        {report.specifications.map((spec, index) => (
          <li key={`${spec.name}-${index}`} className="spec">
            <div className="spec__head">
              <strong>{spec.name || t("report.nothingChecked")}</strong>
              <StatusPill status={spec.status} />
            </div>
            <p className="muted">
              {t("report.matched", { count: spec.matched })} · {spec.cardinality}
            </p>
            {spec.reason_label && <p className="notice">{spec.reason_label}</p>}

            {spec.requirements.map((requirement, requirementIndex) => (
              <div key={requirementIndex} className="requirement">
                <p className="requirement__description">{requirement.description}</p>
                {requirement.entities.length > 0 && (
                  <table className="entities">
                    <tbody>
                      {requirement.entities.map((entity) => (
                        <tr key={`${entity.global_id}-${entity.reason_code}`}>
                          <td>
                            <StatusPill status={entity.status} />
                          </td>
                          <td className="ltr">{entity.ifc_class}</td>
                          <td className="ltr mono">{entity.global_id}</td>
                          <td>{entity.reason_label ?? entity.reason_code}</td>
                          <td className="ltr mono muted">{entity.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {requirement.entities_omitted > 0 && (
                  <p className="muted">
                    {t("report.omitted", { count: requirement.entities_omitted })}
                  </p>
                )}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}
