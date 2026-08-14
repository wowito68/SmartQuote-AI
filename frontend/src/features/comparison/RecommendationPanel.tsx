import { Scale } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  StatusBadge,
  inputClass
} from "../../components/ui";
import { ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import type { UUID } from "../../lib/types";
import { comparisonApi } from "./api";
import type { Comparison, Recommendation, RecommendationCandidate } from "./types";

export function RecommendationPanel({
  comparison,
  userId,
  onError
}: {
  comparison: Comparison;
  userId: UUID;
  onError: (error: unknown) => void;
}) {
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [technical, setTechnical] = useState("");
  const [price, setPrice] = useState("");
  const [delivery, setDelivery] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setRecommendation(null);
    setTechnical("");
    setPrice("");
    setDelivery("");
    void refresh();
  }, [comparison.id]);

  const parsed = useMemo(() => {
    const values = [technical, price, delivery].map((value) =>
      value.trim() === "" ? Number.NaN : Number(value)
    );
    const allValid = values.every(
      (value) => Number.isFinite(value) && value >= 0 && value <= 100
    );
    const sum = allValid
      ? values.reduce((total, value) => total + value, 0)
      : Number.NaN;
    return {
      technical: values[0],
      price: values[1],
      delivery: values[2],
      valid: allValid && Math.abs(sum - 100) < 0.0001,
      sum
    };
  }, [technical, price, delivery]);

  async function refresh() {
    setLoading(true);
    try {
      setRecommendation(await comparisonApi.latestRecommendation(comparison.id));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setRecommendation(null);
      } else {
        onError(error);
      }
    } finally {
      setLoading(false);
    }
  }

  async function generate() {
    if (!parsed.valid) return;
    setGenerating(true);
    try {
      setRecommendation(
        await comparisonApi.generateRecommendation(comparison.id, userId, {
          technical: parsed.technical / 100,
          price: parsed.price / 100,
          delivery: parsed.delivery / 100
        })
      );
    } catch (error) {
      onError(error);
    } finally {
      setGenerating(false);
    }
  }

  if (comparison.status !== "ready") {
    return (
      <EmptyState
        icon={<Scale className="h-5 w-5" />}
        title="Recomendacion no disponible"
        detail="El escenario de recomendacion solo puede calcularse a partir de un comparativo v2 en estado ready."
      />
    );
  }

  return (
    <div className="grid gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-normal text-brand-teal">
          Iteracion 17
        </p>
        <h3 className="mt-1 text-base font-semibold text-text-primary">
          Escenario de recomendacion
        </h3>
        <p className="mt-1 text-sm text-text-secondary">
          Define explicitamente los pesos. El resultado es determinista, explicable y requiere
          revision humana; nunca adjudica la licitacion.
        </p>
      </div>

      <Card>
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end">
          <WeightField
            label="Cumplimiento tecnico (%)"
            value={technical}
            onChange={setTechnical}
          />
          <WeightField label="Precio (%)" value={price} onChange={setPrice} />
          <WeightField label="Entrega (%)" value={delivery} onChange={setDelivery} />
          <Button
            disabled={!parsed.valid}
            loading={generating}
            onClick={() => void generate()}
          >
            Calcular escenario
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <Badge tone={parsed.valid ? "success" : "warning"}>
            {Number.isFinite(parsed.sum)
              ? `Suma: ${parsed.sum}%`
              : "Completa los tres pesos"}
          </Badge>
          <span>Los tres valores deben estar entre 0 y 100 y sumar exactamente 100%.</span>
          <Button
            variant="ghost"
            size="sm"
            loading={loading}
            onClick={() => void refresh()}
          >
            Consultar ultimo
          </Button>
        </div>
      </Card>

      {recommendation ? (
        <RecommendationResult recommendation={recommendation} />
      ) : (
        <EmptyState
          icon={<Scale className="h-5 w-5" />}
          title="Sin escenario calculado"
          detail="No hay pesos predeterminados. Introduce tus criterios y suma 100% para generar un escenario reproducible."
        />
      )}
    </div>
  );
}

function WeightField({
  label,
  value,
  onChange
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium text-text-primary">
      {label}
      <input
        className={inputClass}
        type="number"
        min="0"
        max="100"
        step="1"
        placeholder="0-100"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function RecommendationResult({ recommendation }: { recommendation: Recommendation }) {
  return (
    <div className="grid gap-4">
      <Alert
        tone={recommendation.status === "ready" ? "success" : "warning"}
        title={
          recommendation.status === "ready"
            ? `Proveedor recomendado: ${recommendation.recommended_supplier_name}`
            : "Recomendacion retenida"
        }
        detail={recommendation.explanation}
      />
      <Alert
        tone="info"
        title="Decision humana obligatoria"
        detail="Este resultado es asesor. No cambia el estado de la licitacion, no selecciona un ganador y no ejecuta una adjudicacion."
      />
      <Card padding="sm">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge value={recommendation.status} />
          <Badge>Politica {recommendation.policy_version}</Badge>
          <Badge>
            Humano requerido: {recommendation.human_review_required ? "si" : "no"}
          </Badge>
          <Badge>
            Pesos T/P/E: {percent(recommendation.weights.technical)} /{" "}
            {percent(recommendation.weights.price)} / {percent(recommendation.weights.delivery)}
          </Badge>
        </div>
        <div className="mt-3 grid gap-1 text-xs text-text-secondary sm:grid-cols-2">
          <p>Creado: {formatDate(recommendation.created_at)}</p>
          <p
            className="truncate font-mono"
            title={recommendation.recommendation_key}
          >
            Huella: {recommendation.recommendation_key}
          </p>
        </div>
        {recommendation.warnings.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {recommendation.warnings.map((warning) => (
              <Badge key={warning} tone="warning">
                {warning}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>
      <CandidateTable candidates={recommendation.candidates} />
    </div>
  );
}

function CandidateTable({ candidates }: { candidates: RecommendationCandidate[] }) {
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-text-secondary">
            <tr>
              <th className="px-4 py-3">Proveedor</th>
              <th className="px-4 py-3">Elegible</th>
              <th className="px-4 py-3">Tecnico</th>
              <th className="px-4 py-3">Precio</th>
              <th className="px-4 py-3">Entrega</th>
              <th className="px-4 py-3">Score</th>
              <th className="min-w-80 px-4 py-3">Exclusiones</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => (
              <tr
                key={candidate.supplier_id}
                className="border-t border-border-subtle align-top"
              >
                <td className="px-4 py-3 font-medium text-text-primary">
                  {candidate.supplier_name}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={candidate.eligible ? "success" : "warning"}>
                    {candidate.eligible ? "Si" : "No"}
                  </Badge>
                </td>
                <td className="px-4 py-3">{score(candidate.technical_score)}</td>
                <td className="px-4 py-3">{score(candidate.price_score)}</td>
                <td className="px-4 py-3">{score(candidate.delivery_score)}</td>
                <td className="px-4 py-3 font-semibold">{score(candidate.score)}</td>
                <td className="px-4 py-3">
                  {candidate.exclusion_reasons.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {candidate.exclusion_reasons.map((reason) => (
                        <Badge key={reason} tone="warning">
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <span className="text-text-secondary">Sin exclusiones</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function score(value: string | number | null): string {
  if (value === null) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : String(value);
}

function percent(value: string | number): string {
  const number = Number(value) * 100;
  return Number.isFinite(number) ? `${number.toFixed(0)}%` : "—";
}
