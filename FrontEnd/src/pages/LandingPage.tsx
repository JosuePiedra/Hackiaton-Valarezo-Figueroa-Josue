import { BookOpen, Calculator, MapPin } from 'lucide-react';
import { ChatWindow } from '../components/chat/ChatWindow';

const FEATURES = [
  {
    icon: BookOpen,
    label: 'Cobertura',
    desc: 'Interpreta las reglas de tu plan de seguro',
  },
  {
    icon: Calculator,
    label: 'Copago',
    desc: 'Calcula el monto que deberías pagar',
  },
  {
    icon: MapPin,
    label: 'Prestadores',
    desc: 'Clínicas y médicos de tu red disponibles',
  },
];

export const LandingPage = () => {
  return (
    <div className="flex flex-col flex-1 max-w-5xl mx-auto w-full px-6 py-10 gap-8">
      {/* Hero */}
      <div className="text-center max-w-2xl mx-auto">
        <h1 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight mb-3">
          Calcula tu copago{' '}
          <span className="text-blue-600">antes de ir al médico</span>
        </h1>
        <p className="text-slate-500 text-base">
          Describe tu consulta médica y recibe una estimación de cobertura, copago y prestadores según tu póliza.
        </p>
      </div>

      {/* Feature chips */}
      <div className="flex flex-wrap justify-center gap-3">
        {FEATURES.map(({ icon: Icon, label, desc }) => (
          <div
            key={label}
            className="flex items-center gap-3 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm"
          >
            <div className="w-7 h-7 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0">
              <Icon className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <span className="font-medium text-slate-800">{label}</span>
              <span className="text-slate-400 ml-1.5 hidden sm:inline">{desc}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Chat */}
      <div className="flex-1 min-h-[520px]">
        <ChatWindow />
      </div>
    </div>
  );
};
