import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Any, List, Dict
from dotenv import load_dotenv
from app.models.stateMAD import AssistantMessageContent
from app.manager.Mongo import Mongo
from app.models.chat import Message, Conversation
from app.utils.generate_name_conversation import format_name, generate_name

class LLMStrategy(ABC):
    def __init__(self, model_name: Optional[str], session_id: Optional[str] = None, distributor: str = None):
        """
        Inicializa la estrategia con el modelo y parámetros opcionales de sesión.
        
        Args:
            model_name: Nombre del modelo a usar
            session_id: ID de sesión para mantener el contexto de la conversación
            distributor: Nombre del distribuidor del modelo
        """
        load_dotenv()
        self.model_name = model_name
        self.session_id = session_id
        self.distributor = distributor
        self.db = Mongo.get_instance()
        self.llm = self._initialize_llm()



    def _get_conversation_history(self, session_provitional_id: Optional[str]) -> Dict:
        """
        Obtiene y formatea el historial de la conversación desde MongoDB, devolviendo un JSON con los mensajes.

        Returns:
            Dict: Un diccionario JSON con la lista de mensajes formateados.
        """
        if session_provitional_id:
            self.session_id = session_provitional_id
        if not self.session_id:
            return {"messages": {}}  # Retorna un JSON vacío si no hay session_id

        try:
            # Acceder directamente a la colección
            conversation_doc = self.db['conversations'].find_one({"session_id": self.session_id})
            if not conversation_doc or not conversation_doc.get("messages"):
                return {"messages": {}}  # Retorna un JSON vacío si no hay conversación o mensajes

            # Convertir el documento a un objeto Conversation
            conversation = Conversation(**conversation_doc)

            messages_list: List[Dict[str, Any]] = []
            for msg in conversation.messages[-5:]:  # Últimos 5 mensajes
                if isinstance(msg.content, dict):
                    try:
                        assistant_message_content = AssistantMessageContent(**msg.content)
                        for inner_msg_content in assistant_message_content.messages:
                            # Verificar estado y calificación
                            is_active = getattr(inner_msg_content, 'status', 'active') == 'active'
                            has_valid_calification = True

                            if inner_msg_content.type == "assistant":
                                has_valid_calification = getattr(inner_msg_content, 'calification', True) is not False

                            if is_active and has_valid_calification:
                                message_dict = {
                                    "id": inner_msg_content.id,
                                    "content": inner_msg_content.content,
                                    "type": inner_msg_content.type,
                                    "name": inner_msg_content.name if hasattr(inner_msg_content, 'name') else None,
                                    "status": "active"
                                }
                                if inner_msg_content.type == "assistant" and hasattr(inner_msg_content, 'calification'):
                                    message_dict["calification"] = inner_msg_content.calification
                                messages_list.append(message_dict)
                    except (ValueError, AttributeError) as e:
                        logging.error(f"Error al procesar mensaje: {e}")
                        continue
                else:
                    # Omitir mensajes que no son diccionarios
                    continue

            return {"messages": messages_list}

        except Exception as e:
            logging.error(f"Error al obtener el historial de conversación: {e}")
            return {"messages": {}}

    def _is_new_conversation(self) -> bool:
        """
        Verifica si es una nueva conversación chequeando el historial.

        Returns:
            bool: True si es una nueva conversación, False si ya existe
        """
        if not self.session_id:
            return True

        conversation_doc = self.db['conversations'].find_one({"session_id": self.session_id})
        return conversation_doc is None or len(conversation_doc.get("messages", [])) == 0

    def _generate_conversation_name(self, response: str) -> Optional[str]:
        """
        Genera un nombre para una nueva conversación.

        Args:
            response: La respuesta del modelo para usar como base del nombre

        Returns:
            str: El nombre generado y formateado, o None si no se pudo generar
        """
        if not self._is_new_conversation():
            return None

        try:
            conversation_name = generate_name(response, self.llm)
            return format_name(conversation_name)
        except Exception as e:
            print(f"Error al generar el nombre de la conversación: {str(e)}")
            return None

    def generate_response(self, prompt: str) -> dict[str, str | None | Any]:
        """
        Genera una respuesta considerando el historial de la conversación si existe session_id.

        Args:
            prompt: El texto de entrada para generar la respuesta

        Returns:
            str: La respuesta generada por el modelo
        """
        # Verificar que prompt no sea None
        prompt_content = prompt if prompt is not None else "Hola, ¿en qué puedo ayudarte?"

        default_prompt = """
        Eres un asistente inteligente que responde en español y utiliza Markdown para formatear tus respuestas.
        Siempre mantén un tono amigable y profesional (No agregues Emojis).
        Asegúrate de entender el contexto proporcionado antes de responder.
        """

        # Construir el prompt completo con contexto si existe
        context = self._get_conversation_history() if self.session_id else ""
        full_prompt = f"{default_prompt}{context}user: {prompt_content}\nassistant:"

        # Generar respuesta usando el LLM específico
        response = self.llm.invoke(full_prompt)
        final_response = response.content if hasattr(response, 'content') else str(response)

        # Generar nombre si es una nueva conversación
        conversation_name = None
        if self.session_id:
            conversation_name = self._generate_conversation_name(final_response)

            # Guardar mensajes en la base de datos
            self._save_messages_to_db(prompt_content, final_response, conversation_name)
        else:
            conversation_name = "TEST"

        return {
            "content": final_response,
            "conversation_name": conversation_name,
        }
    def _save_messages_to_db(self, prompt: str, final_response: Any, conversation_name: Optional[str]):
        """
        Guarda los mensajes del usuario y del asistente en la base de datos.

        Args:
            prompt: El texto de entrada del usuario.
            final_response: La respuesta generada por el modelo.
            conversation_name: El nombre de la conversación (si es una nueva conversación).
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Attempting to save messages with session_id: {self.session_id}")
        logger.debug(f"Prompt type: {type(prompt)}, Final response type: {type(final_response)}")
        if not self.session_id:
            logger.warning("No session_id provided, skipping database save")
            return

        collection = self.db['conversations']

        # Crear mensaje del usuario
        try:
            user_message = Message(content=prompt)
            logger.debug(f"Created user message: {user_message}")
        except Exception as e:
            logger.error(f"Error creating user message: {str(e)}")
            return

        # Buscar conversación existente
        try:
            conversation_doc = collection.find_one({"session_id": self.session_id})
            logger.debug(f"Found existing conversation: {bool(conversation_doc)}")
        except Exception as e:
            logger.error(f"Error finding conversation: {str(e)}")
            return

        if conversation_doc:
            # Actualizar conversación existente con mensaje del usuario
            try:
                conversation = Conversation(**conversation_doc)
                conversation.messages.append(user_message)
                conversation.last_updated = datetime.utcnow()

                update_data = {
                    "messages": [msg.dict() for msg in conversation.messages],
                    "last_updated": conversation.last_updated
                }

                collection.update_one(
                    {"session_id": self.session_id},
                    {"$set": update_data}
                )
                logger.info(f"Updated conversation with user message, message count: {len(conversation.messages)}")
            except Exception as e:
                logger.error(f"Error updating conversation with user message: {str(e)}")
        else:
            # Crear nueva conversación
            try:
                conversation = Conversation(
                    session_id=self.session_id,
                    distributor=self.distributor,
                    model=self.model_name,
                    name=conversation_name,
                    messages=[user_message]
                )
                collection.insert_one(conversation.dict())
                logger.info(f"Created new conversation with name: {conversation_name}")
            except Exception as e:
                logger.error(f"Error creating new conversation: {str(e)}")
                return

        # Guardar mensaje del asistente
        try:
            # No extraer ni convertir, simplemente guarda final_response directamente
            assistant_message = Message(
                content=final_response,  # Guarda final_response como está
                model=self.model_name
            )
            logger.debug(f"Created assistant message: {assistant_message}")
        except Exception as e:
            logger.error(f"Error creating assistant message: {str(e)}")
            return

        # Actualizar con mensaje del asistente
        try:
            conversation_doc = collection.find_one({"session_id": self.session_id})
            if conversation_doc:
                conversation = Conversation(**conversation_doc)
                conversation.messages.append(assistant_message)
                conversation.last_updated = datetime.utcnow()

                update_data = {
                    "messages": [msg.dict() for msg in conversation.messages],
                    "last_updated": conversation.last_updated
                }

                collection.update_one(
                    {"session_id": self.session_id},
                    {"$set": update_data}
                )
                logger.info(f"Updated conversation with assistant message, message count: {len(conversation.messages)}")
            else:
                logger.warning(f"Could not find conversation to update with assistant message")
        except Exception as e:
            logger.error(f"Error updating conversation with assistant message: {str(e)}")