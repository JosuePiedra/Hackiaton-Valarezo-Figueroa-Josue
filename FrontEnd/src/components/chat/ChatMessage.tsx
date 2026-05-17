import React from 'react';
import {
  Bot,
  User,
  AlertCircle,
  Building2,
  Stethoscope,
  DollarSign,
  ShieldCheck,
  Clock,
  Network,
  FileText,
} from 'lucide-react';
import type { ResponseType } from '../../api/insuranceApi';
import { PlanSelector } from './PlanSelector';

export interface MessageProps {
  id: string;
  isUser: boolean;
  content: string;
  response_type?: ResponseType;
  // plan_selection
  plans?: string[];
  // coverage_info
  specialty?: string;
  estimated_copay?: string;
  requires_authorization?: boolean;
  waiting_period_days?: number;
  network_tier?: string;
  providers?: string[];
  annual_deductible?: string;
  notes?: string;
  deductible_applies?: boolean;
  isLoading?: boolean;
  onPlanSelect?: (plan: string) => void;
}

interface InfoCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
}

const InfoCard: React.FC<InfoCardProps> = ({ icon, label, value, highlight }) => (
  <div className={`flex items-start gap-3 p-3 rounded-xl border ${
    highlight
      ? 'bg-blue-50 border-blue-200'
      : 'bg-white border-slate-200'
  }`}>
    <div className={`mt-0.5 flex-shrink-0 ${highlight ? 'text-blue-600' : 'text-slate-400'}`}>
      {icon}
    </div>
    <div>
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-0.5">{label}</p>
      <p className={`text-sm font-semibold ${highlight ? 'text-blue-700' : 'text-slate-700'}`}>{value}</p>
    </div>
  </div>
);

// Removes markdown coverage bullet lists that duplicate card data
function cleanReply(text: string, type?: ResponseType): string {
  if (type !== 'coverage_info') return text;
  return text
    .split('\n')
    .filter(line => !line.match(/^\s*[\*\-]\s+\*\*(Especialidad|Copago|Requiere|Período|Tipo de red|Proveedor|Deducible|Red médica|Autorización)/i))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export const ChatMessage: React.FC<MessageProps> = ({
  isUser,
  content,
  response_type,
  plans,
  specialty,
  estimated_copay,
  requires_authorization,
  waiting_period_days,
  network_tier,
  providers,
  annual_deductible,
  notes,
  deductible_applies,
  isLoading,
  onPlanSelect,
}) => {
  const isCoverage = response_type === 'coverage_info';
  const isPlanSelection = response_type === 'plan_selection' && plans && plans.length > 0;
  const displayText = cleanReply(content, response_type);

  return (
    <div className={`flex w-full px-4 py-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-2xl gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500'
        }`}>
          {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
        </div>

        <div className={`flex flex-col gap-2 ${isUser ? 'items-end' : 'items-start w-full'}`}>
          {/* Bubble */}
          <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? 'bg-blue-600 text-white rounded-tr-sm'
              : isCoverage
              ? 'bg-white border border-slate-200 text-slate-500 rounded-tl-sm'
              : 'bg-slate-50 border border-slate-200 text-slate-800 rounded-tl-sm'
          }`}>
            {isLoading ? (
              <div className="flex gap-1 items-center h-4">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            ) : (
              <p className="whitespace-pre-wrap">{displayText}</p>
            )}
          </div>

          {/* Plan selector chips */}
          {!isUser && !isLoading && isPlanSelection && (
            <PlanSelector
              plans={plans!}
              onSelect={(plan) => onPlanSelect?.(plan)}
            />
          )}

          {/* Coverage info cards */}
          {!isUser && !isLoading && isCoverage && (
            <div className="w-full space-y-2 mt-1">
              <div className="grid grid-cols-2 gap-2">
                {specialty && (
                  <InfoCard
                    icon={<Stethoscope className="w-4 h-4" />}
                    label="Especialidad"
                    value={specialty}
                  />
                )}
                {estimated_copay && (
                  <InfoCard
                    icon={<DollarSign className="w-4 h-4" />}
                    label="Copago estimado"
                    value={estimated_copay}
                    highlight
                  />
                )}
                {annual_deductible && (
                  <InfoCard
                    icon={<FileText className="w-4 h-4" />}
                    label="Deducible anual"
                    value={`${annual_deductible}${deductible_applies === false ? ' · no aplica' : ''}`}
                  />
                )}
                {network_tier && (
                  <InfoCard
                    icon={<Network className="w-4 h-4" />}
                    label="Red médica"
                    value={network_tier}
                  />
                )}
                {requires_authorization !== undefined && requires_authorization !== null && (
                  <InfoCard
                    icon={<ShieldCheck className="w-4 h-4" />}
                    label="Autorización previa"
                    value={requires_authorization ? 'Requerida' : 'No requerida'}
                  />
                )}
                {waiting_period_days !== undefined && waiting_period_days !== null && (
                  <InfoCard
                    icon={<Clock className="w-4 h-4" />}
                    label="Período de espera"
                    value={waiting_period_days === 0 ? 'Sin período de espera' : `${waiting_period_days} días`}
                  />
                )}
              </div>

              {/* Providers */}
              {providers && providers.length > 0 && (
                <div className="bg-white border border-slate-200 p-3 rounded-xl">
                  <div className="flex items-center gap-2 mb-2">
                    <Building2 className="w-4 h-4 text-slate-400" />
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Prestadores disponibles</p>
                  </div>
                  <ul className="space-y-1">
                    {providers.map((p, i) => (
                      <li key={i} className="text-sm text-slate-700 flex items-center gap-2">
                        <span className="w-1 h-1 rounded-full bg-blue-400 flex-shrink-0" />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Notes */}
              {notes && (
                <div className="bg-amber-50 border border-amber-100 p-3 rounded-xl flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-amber-800">{notes}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
