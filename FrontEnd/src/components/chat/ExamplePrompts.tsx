import React from 'react';

interface ExamplePromptsProps {
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}

const EXAMPLES = [
  "Consulta con pediatra",
  "Me duele la rodilla, estoy en Guayaquil",
  "Exámenes de laboratorio",
  "¿Mi seguro cubre hospitalización?",
];

export const ExamplePrompts: React.FC<ExamplePromptsProps> = ({ onSelect, disabled }) => {
  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {EXAMPLES.map((example, i) => (
        <button
          key={i}
          onClick={() => onSelect(example)}
          disabled={disabled}
          className="text-sm px-4 py-2 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 text-slate-600 rounded-full transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {example}
        </button>
      ))}
    </div>
  );
};
