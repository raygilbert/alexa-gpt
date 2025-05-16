from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.interfaces.alexa.presentation.apl import RenderDocumentDirective
from ask_sdk_model.ui import StandardCard, SimpleCard
import ask_sdk_core.utils as ask_utils
import requests
import logging
import json
from config import OPENAI_API_KEY, MODEL_CONFIG

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_api_key():
    if not OPENAI_API_KEY or OPENAI_API_KEY == "YOUR_API_KEY":
        logger.error("OpenAI API key not configured in config.py")
        raise ValueError("OpenAI API key not configured")
    return OPENAI_API_KEY

def supports_apl(handler_input):
    try:
        supported_interfaces = handler_input.request_envelope.context.system.device.supported_interfaces
        has_apl = hasattr(supported_interfaces, 'alexa_presentation_apl')
        logger.info(f"Device supports APL: {has_apl}")
        return has_apl
    except Exception as e:
        logger.error(f"Error checking APL support: {str(e)}", exc_info=True)
        return False

def create_apl_directive(handler_input, title, primary_text, secondary_text=None):
    try:
        if supports_apl(handler_input):
            logger.info("Creating APL Sequence directive")
            
            # Create an APL document
            apl_document = {
                "type": "APL",
                "version": "1.5",
                "theme": "dark",
                "mainTemplate": {
                    "parameters": [
                        "payload"
                    ],
                    "items": [
                        {
                            "type": "Container",
                            "width": "100vw",
                            "height": "100vh",  # Changed from 100vw to 100vh
                            "items": [
                                {
                                    "type": "Sequence",
                                    "width": "100%",
                                    "height": "100%",
                                    "data": "${payload.sequenceData}",  # Update this reference
                                    "numbered": False,  
                                    "scrollDirection": "vertical",
                                    "backgroundVisible": False, 
                                    "items": [
                                        {
                                            "type": "Text",
                                            "id": "titleText",
                                            "width": "100vw",
                                            "paddingTop": "40dp",
                                            "paddingBottom": "20dp",
                                            "textAlign": "center",
                                            "textAlignVertical": "center",
                                            "fontSize": "24dp",
                                            "fontWeight": "bold",
                                            "text": "${data.titleText}"
                                        },
                                        {
                                            "type": "Text",
                                            "id": "primaryText",
                                            "width": "100vw",
                                            "paddingLeft": "15dp",
                                            "paddingRight": "15dp",
                                            "paddingBottom": "20dp",
                                            "textAlign": "left",
                                            "fontSize": "20dp",
                                            "text": "${data.primaryText}"
                                        },
                                        {
                                            "type": "Text",
                                            "id": "secondaryText",
                                            "width": "100vw",
                                            "paddingLeft": "15dp",
                                            "paddingRight": "15dp",
                                            "textAlign": "left",
                                            "fontSize": "20dp",
                                            "text": "${data.secondaryText}"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }
            
            # Change the datasources to be an object (not an array)
            datasources = {
                "payload": {
                    "sequenceData": [  # Move the array here
                        {
                            "titleText": title,
                            "primaryText": primary_text,
                            "secondaryText": secondary_text or ""
                        }
                    ]
                }
            }
            
            logger.info(f"APL Sequence Document: {json.dumps(apl_document)[:200]}...")
            logger.info(f"Sequence Datasources: {json.dumps(datasources)}")
            
            return RenderDocumentDirective(
                token="token",
                document=apl_document,
                datasources=datasources
            )
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error creating APL Directive: {str(e)}", exc_info=True)
        return None

def generate_gpt_response(chat_history, new_question):
    try:
        api_key = get_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        url = "https://api.openai.com/v1/chat/completions"

        messages = [{"role": "system", "content": "You are a helpful assistant. Provide clear, concise answers. Keep responses under 50 words."}]
        for q, a in chat_history[-5:]:
            messages.append({"role": "user", "content": q})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": new_question})

        data = {"messages": messages, **MODEL_CONFIG}
        logger.info(f"Sending request to OpenAI API")
        res = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        
        if res.ok:
            response_text = res.json()['choices'][0]['message']['content'].strip()
            logger.info(f"Received response from OpenAI API: {response_text[:50]}...")
            return response_text
        else:
            logger.error(f"OpenAI error: {res.status_code} - {res.text}")
            return "I'm having trouble connecting right now. Please try again."

    except Exception as e:
        logger.error(f"Error generating GPT response: {e}", exc_info=True)
        return "I encountered an error processing your request."

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speak_output = "Chat G.P.T. mode activated"
        handler_input.attributes_manager.session_attributes["chat_history"] = []

        # Create response builder
        rb = handler_input.response_builder
        rb.speak(speak_output).ask(speak_output)

        # Always add a card for non-screen devices
        rb.set_card(
            StandardCard(
                title="Welcome to ChatGPT",
                text="ChatGPT Mode is now active.\n\nYou can ask me any question!\n\nI'm ready to help you find answers."
            )
        )
        
        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Launch - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="Welcome to ChatGPT",
                primary_text="ChatGPT Mode is now active.\n\nYou can ask me any question!",
                secondary_text="I'm ready to help you find answers."
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to launch response")
            else:
                logger.error("Failed to create APL directive")

        return rb.response

class GptQueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GptQueryIntent")(handler_input)

    def handle(self, handler_input):
        query = handler_input.request_envelope.request.intent.slots["query"].value
        session_attr = handler_input.attributes_manager.session_attributes
        chat_history = session_attr.setdefault("chat_history", [])

        logger.info(f"Processing query: {query}")
        response = generate_gpt_response(chat_history, query)
        chat_history.append((query, response))

        speak_output = f"{response} Would you like to ask another question?"

        # Create response builder
        rb = handler_input.response_builder
        rb.speak(speak_output).ask("Would you like to ask another question?")

        # Always add a card for non-screen devices
        rb.set_card(
            StandardCard(
                title="ChatGPT Response",
                text=f"Question:\n{query}\n\nAnswer:\n{response}\n\nWould you like to ask another question?"
            )
        )
        
        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Query - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="ChatGPT Response",
                primary_text=f"Question:\n{query}\n\nAnswer:\n{response}",
                secondary_text="Would you like to ask another question?"
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to query response")
            else:
                logger.error("Failed to create APL directive")

        return rb.response

class YesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "What would you like to know?"

        rb = handler_input.response_builder
        rb.speak(speak_output).ask(speak_output)
        
        # Always add a card for non-screen devices
        rb.set_card(
            SimpleCard(
                title="Ask Another Question",
                content="What would you like to know?"
            )
        )

        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Yes - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="Ask Another Question",
                primary_text="What would you like to know?",
                secondary_text="I'm ready to help!"
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to yes response")
            else:
                logger.error("Failed to create APL directive")

        return rb.response

class NoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "Thanks for chatting! Goodbye."
        
        rb = handler_input.response_builder
        rb.speak(speak_output).set_should_end_session(True)
        
        # Always add a card for non-screen devices
        rb.set_card(
            SimpleCard(
                title="Goodbye",
                content="Thanks for chatting! Have a great day!"
            )
        )

        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("No - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="Goodbye",
                primary_text="Thanks for chatting!",
                secondary_text="Have a great day!"
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to no response")
            else:
                logger.error("Failed to create APL directive")

        return rb.response

class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "You can ask me any question, and I'll use ChatGPT to provide an answer. Just speak your question clearly."
        
        rb = handler_input.response_builder.speak(speak_output).ask(speak_output)
        
        # Add a card
        rb.set_card(
            SimpleCard(
                title="Help with ChatGPT",
                content=speak_output
            )
        )
        
        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Help - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="How to Use ChatGPT",
                primary_text="You can ask me any question, and I'll use ChatGPT to provide an answer.",
                secondary_text="Just speak your question clearly."
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to help response")
                
        return rb.response

class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (
            ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
            ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
        )

    def handle(self, handler_input):
        speak_output = "Leaving Chat G.P.T. mode"
        
        rb = handler_input.response_builder
        rb.speak(speak_output).set_should_end_session(True)
        
        # Add a card
        rb.set_card(
            SimpleCard(
                title="Goodbye",
                content="Leaving ChatGPT Mode. Thanks for chatting!"
            )
        )

        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Cancel/Stop - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="Goodbye",
                primary_text="Leaving ChatGPT Mode",
                secondary_text="Thanks for chatting!"
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to cancel/stop response")

        return rb.response

class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "I'm not sure what you're asking. You can ask me any question, and I'll try to provide an answer using ChatGPT."
        
        rb = handler_input.response_builder.speak(speak_output).ask(speak_output)
        
        # Add a card
        rb.set_card(
            SimpleCard(
                title="I Didn't Understand",
                content=speak_output
            )
        )
        
        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            logger.info("Fallback - Device has APL capabilities")
            directive = create_apl_directive(
                handler_input,
                title="I Didn't Understand",
                primary_text="I'm not sure what you're asking.",
                secondary_text="You can ask me any question, and I'll try to provide an answer using ChatGPT."
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to fallback response")
                
        return rb.response

class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        reason = "unknown"
        if hasattr(handler_input.request_envelope.request, 'reason'):
            reason = handler_input.request_envelope.request.reason
        
        logger.info(f"Session ended with reason: {reason}")
        
        if hasattr(handler_input.request_envelope.request, 'error'):
            error = handler_input.request_envelope.request.error
            logger.error(f"Session ended error details: {json.dumps(error.__dict__) if hasattr(error, '__dict__') else error}")
            
        return handler_input.response_builder.response

class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(exception, exc_info=True)
        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        rb = handler_input.response_builder.speak(speak_output).ask(speak_output)
        
        # Add a card
        rb.set_card(
            SimpleCard(
                title="Error Occurred",
                content="Sorry, I had trouble doing what you asked. Please try again."
            )
        )
        
        # For devices with screens, add APL directive
        if supports_apl(handler_input):
            directive = create_apl_directive(
                handler_input,
                title="Error Occurred",
                primary_text="Sorry, I had trouble doing what you asked.",
                secondary_text="Please try again."
            )
            if directive:
                rb.add_directive(directive)
                logger.info("Added APL directive to exception response")

        return rb.response

# Create skill builder
sb = SkillBuilder()

# Add request handlers
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(GptQueryIntentHandler())
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(NoIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())  # Add the SessionEndedRequestHandler

# Add exception handler
sb.add_exception_handler(CatchAllExceptionHandler())

# Lambda handler
lambda_handler = sb.lambda_handler()