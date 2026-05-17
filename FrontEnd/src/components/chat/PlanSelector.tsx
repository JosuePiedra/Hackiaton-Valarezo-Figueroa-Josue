import React from 'react';
import { Shield } from 'lucide-react';

interface PlanSelectorProps {
  plans: string[];
  onSelect: (plan: string) => void;
  disabled?: boolean;
}

export const PlanSelector: React.FC<PlanSelectorProps> = ({ plans, onSelect, disabled }) => {
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {plans.map((plan) => (
        <button
          key={plan}
          onClick={() => onSelect(plan)}
          disabled={disabled}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-blue-200 hover:border-blue-500 hover:bg-blue-50 text-blue-700 text-sm font-medium rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Shield className="w-3.5 h-3.5 flex-shrink-0" />
          {plan}
        </button>
      ))}
    </div>
  );
};
