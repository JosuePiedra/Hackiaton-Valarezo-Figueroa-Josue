import React, { useState, useRef } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { uploadInsuranceDocument } from '../../api/insuranceApi';

type Status = 'idle' | 'uploading' | 'processing' | 'success' | 'error';

const PIPELINE_STEPS = [
  'Carga del archivo',
  'OCR / Parser',
  'Extracción de reglas',
  'Normalización',
  'Guardado en base de datos',
];

export const UploadInsuranceForm = () => {
  const [nombreSeguro, setNombreSeguro] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const acceptFile = (f: File) => {
    if (f.type === 'application/pdf' || f.name.endsWith('.xlsx') || f.name.endsWith('.xls')) {
      setFile(f);
      setStatus('idle');
      setMessage('');
    } else {
      setStatus('error');
      setMessage('Formato no soportado. Sube un archivo PDF, .xlsx o .xls.');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) acceptFile(e.target.files[0]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.[0]) acceptFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !nombreSeguro.trim()) {
      setStatus('error');
      setMessage('Completa todos los campos.');
      return;
    }

    setStatus('uploading');
    setMessage('Subiendo documento...');

    try {
      setStatus('processing');
      setMessage('Extrayendo reglas de cobertura...');
      await uploadInsuranceDocument(file, nombreSeguro.trim());
      setStatus('success');
      setMessage('Documento procesado y disponible en el chatbot.');
      setFile(null);
      setNombreSeguro('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch {
      setStatus('error');
      setMessage('Error al procesar el documento. Intenta nuevamente.');
    }
  };

  const isProcessing = status === 'uploading' || status === 'processing';

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">Cargar póliza o red médica</h2>
        <p className="text-sm text-slate-500">
          Sube un PDF o Excel para que el agente extraiga reglas de cobertura, copagos y prestadores.
        </p>
      </div>

      {/* Pipeline */}
      <div className="flex items-center gap-1 flex-wrap">
        {PIPELINE_STEPS.map((step, i) => (
          <React.Fragment key={step}>
            <span className={`text-xs px-2.5 py-1 rounded-full border ${status === 'success'
                ? 'bg-blue-50 border-blue-200 text-blue-700'
                : 'bg-slate-50 border-slate-200 text-slate-500'
              }`}>
              {step}
            </span>
            {i < PIPELINE_STEPS.length - 1 && (
              <ArrowRight className="w-3 h-3 text-slate-300 flex-shrink-0" />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-2xl p-6 space-y-5">
        <div>
          <label htmlFor="nombre_seguro" className="block text-sm font-medium text-slate-700 mb-1.5">
            Nombre del seguro o plan <span className="text-blue-500">*</span>
          </label>
          <input
            id="nombre_seguro"
            type="text"
            value={nombreSeguro}
            onChange={e => setNombreSeguro(e.target.value)}
            placeholder="Ej. INSPIRA SEGURO BÁSICO"
            disabled={isProcessing}
            className="w-full px-4 py-2.5 text-sm rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition-all placeholder:text-slate-400 disabled:opacity-60"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Documento <span className="text-blue-500">*</span>
          </label>
          <div
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all select-none ${isProcessing
                ? 'opacity-50 pointer-events-none border-slate-200'
                : isDragging
                  ? 'border-blue-400 bg-blue-50'
                  : file
                    ? 'border-blue-300 bg-blue-50/50'
                    : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
              }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.xlsx,.xls"
              className="hidden"
            />
            {file ? (
              <div className="flex flex-col items-center gap-2">
                <FileText className="w-8 h-8 text-blue-500" />
                <p className="text-sm font-medium text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-400">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center mb-1">
                  <Upload className="w-5 h-5 text-slate-400" />
                </div>
                <p className="text-sm text-slate-600">Haz clic o arrastra un archivo aquí</p>
                <p className="text-xs text-slate-400">PDF, XLSX o XLS</p>
              </div>
            )}
          </div>
        </div>

        {status !== 'idle' && (
          <div className={`flex items-start gap-3 p-4 rounded-xl text-sm ${status === 'error'
              ? 'bg-red-50 border border-red-100 text-red-700'
              : status === 'success'
                ? 'bg-green-50 border border-green-100 text-green-700'
                : 'bg-blue-50 border border-blue-100 text-blue-700'
            }`}>
            {status === 'error' && <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />}
            {status === 'success' && <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />}
            {isProcessing && <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin" />}
            <div className="flex-1">
              <p>{message}</p>
              {isProcessing && (
                <div className="w-full bg-blue-200 rounded-full h-1 mt-3 overflow-hidden">
                  <div className="bg-blue-500 h-1 rounded-full w-3/4 animate-pulse" />
                </div>
              )}
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={!file || !nombreSeguro.trim() || isProcessing}
          className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed flex justify-center items-center gap-2"
        >
          {isProcessing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Procesando...
            </>
          ) : (
            'Procesar documento'
          )}
        </button>
      </form>
    </div>
  );
};
