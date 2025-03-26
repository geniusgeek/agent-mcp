"""
MCPAgent - An AutoGen agent with Model Context Protocol capabilities.

This module provides a transparent implementation of the Model Context Protocol
for AutoGen agents, allowing them to standardize context provision to LLMs and
interact with other MCP-capable systems with minimal configuration.
"""

import json
import uuid
import inspect
from typing import Any, Dict, List, Optional, Union, Callable, Tuple

# Import AutoGen
from autogen import ConversableAgent, Agent


class MCPAgent(ConversableAgent):
    """
    An AutoGen agent with Model Context Protocol capabilities.

    This agent extends the ConversableAgent to implement the Model Context Protocol,
    enabling standardized context provision to LLMs and seamless interaction with
    other MCP-capable systems.

    Attributes:
        context_store (Dict): Store for the agent's current context
        mcp_tools (Dict): Dictionary of MCP tools available to this agent
        mcp_id (str): Unique identifier for this MCP agent
        mcp_version (str): The MCP version implemented by this agent
    """

    def __init__(
        self,
        name: str,
        system_message: Optional[str] = None,
        is_termination_msg: Optional[Callable[[Dict], bool]] = None,
        max_consecutive_auto_reply: Optional[int] = None,
        human_input_mode: str = "NEVER",
        **kwargs,
    ):
        """
        Initialize an MCPAgent.

        Args:
            name: The name of the agent
            system_message: System message for the agent
            is_termination_msg: Function to determine if a message should terminate a conversation
            max_consecutive_auto_reply: Maximum number of consecutive automated replies
            human_input_mode: Human input mode setting
            **kwargs: Additional keyword arguments passed to ConversableAgent
        """
        if system_message is None:
            system_message = (
                "You are an AI assistant that follows the Model Context Protocol (MCP). "
                "You can access and manipulate context through the provided MCP tools. "
                "Use these tools to enhance your responses with relevant information."
            )

        super().__init__(
            name=name,
            system_message=system_message,
            is_termination_msg=is_termination_msg,
            max_consecutive_auto_reply=max_consecutive_auto_reply,
            human_input_mode=human_input_mode,
            **kwargs,
        )

        # MCP specific attributes
        self.context_store = {}
        self.mcp_tools = {}
        self.mcp_id = str(uuid.uuid4())
        self.mcp_version = "0.1.0"  # MCP version implemented

        # Register default MCP tools
        self._register_default_mcp_tools()

    def _register_default_mcp_tools(self):
        """Register default MCP tools that are available to all MCP agents."""
        
        # Context management tools
        def context_get(key: str) -> Dict:
            """Get a context item by key."""
            return self._mcp_context_get(key)
            
        def context_set(key: str, value: Any) -> Dict:
            """Set a context item with the given key and value."""
            return self._mcp_context_set(key, value)
            
        def context_list() -> Dict:
            """List all available context keys."""
            return self._mcp_context_list()
            
        def context_remove(key: str) -> Dict:
            """Remove a context item by key."""
            return self._mcp_context_remove(key)
            
        def mcp_info() -> Dict:
            """Get information about this MCP agent's capabilities."""
            return self._mcp_info()
        
        # Register the tools with valid names for AutoGen (only letters, numbers, underscore, dash)
        self.register_mcp_tool(
            name="context_get",
            description="Get a specific context item by key",
            func=context_get,
            key_description="The key of the context item to retrieve"
        )
        
        self.register_mcp_tool(
            name="context_set",
            description="Set a context item with the given key and value",
            func=context_set,
            key_description="The key to store the value under",
            value_description="The value to store"
        )
        
        self.register_mcp_tool(
            name="context_list",
            description="List all available context keys",
            func=context_list
        )
        
        self.register_mcp_tool(
            name="context_remove",
            description="Remove a context item by key",
            func=context_remove,
            key_description="The key of the context item to remove"
        )

        # Metadata tools
        self.register_mcp_tool(
            name="mcp_info",
            description="Get information about this MCP agent's capabilities",
            func=mcp_info
        )

    def register_mcp_tool(
        self, name: str, description: str, func: Callable, **kwargs
    ) -> None:
        """
        Register an MCP tool with this agent.

        Args:
            name: The name of the tool, used for invocation
            description: Description of what the tool does
            func: The function to be called when the tool is invoked
            **kwargs: Additional tool configuration
        """
        if name in self.mcp_tools:
            print(f"Warning: Overriding existing MCP tool '{name}'")

        # Inspect function signature to build parameter info
        sig = inspect.signature(func)
        params = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_info = {
                "name": param_name,
                "description": kwargs.get(f"{param_name}_description", f"Parameter {param_name}"),
                "required": param.default == inspect.Parameter.empty
            }
            
            # Add type information if available
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = str(param.annotation.__name__)
                
            params.append(param_info)

        # Register the tool
        self.mcp_tools[name] = {
            "name": name,
            "description": description,
            "parameters": params,
            "function": func,
        }

        # Create a wrapper that calls the function correctly
        # For functions defined within context_management, they already handle self
        def tool_wrapper(**kwargs):
            return func(**kwargs)
        
        # Register the tool with AutoGen's function mechanism
        function_schema = {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        # Add parameter descriptions to the schema
        for param in params:
            param_name = param["name"]
            function_schema["parameters"]["properties"][param_name] = {
                "type": param.get("type", "string"),
                "description": param["description"]
            }
            if param["required"]:
                function_schema["parameters"]["required"].append(param_name)
        
        # Register with AutoGen - use the simplest form
        self.register_function({name: tool_wrapper})

    def register_agent_as_tool(self, agent: Agent, name: Optional[str] = None) -> None:
        """
        Register another agent as a tool that can be called by this agent.

        Args:
            agent: The agent to register as a tool
            name: Optional custom name for the tool, defaults to agent's name
        """
        if name is None:
            # Use valid characters for AutoGen
            name = f"agent_{agent.name}"
            
        def agent_tool_wrapper(message: str, **kwargs):
            """Wrapper to call another agent and return its response."""
            response = agent.generate_reply(sender=self, messages=[{"role": "user", "content": message}])
            return {"response": response if response else "No response from agent."}
            
        self.register_mcp_tool(
            name=name,
            description=f"Send a message to agent '{agent.name}' and get their response",
            func=agent_tool_wrapper,
            message_description="The message to send to the agent"
        )

    # MCP Context Tool Implementations
    def _mcp_context_get(self, key: str) -> Dict:
        """
        Get a context item by key.
        
        Args:
            key: The key of the context item to retrieve
            
        Returns:
            Dict containing the value or an error message
        """
        if key in self.context_store:
            return {"status": "success", "value": self.context_store[key]}
        return {"status": "error", "message": f"Key '{key}' not found in context"}

    def _mcp_context_set(self, key: str, value: Any) -> Dict:
        """
        Set a context item with the given key and value.
        
        Args:
            key: The key to store the value under
            value: The value to store
            
        Returns:
            Dict indicating success or failure
        """
        self.context_store[key] = value
        return {"status": "success", "message": f"Context key '{key}' set successfully"}

    def _mcp_context_list(self) -> Dict:
        """
        List all available context keys.
        
        Returns:
            Dict containing the list of context keys
        """
        return {"status": "success", "keys": list(self.context_store.keys())}

    def _mcp_context_remove(self, key: str) -> Dict:
        """
        Remove a context item by key.
        
        Args:
            key: The key of the context item to remove
            
        Returns:
            Dict indicating success or failure
        """
        if key in self.context_store:
            del self.context_store[key]
            return {"status": "success", "message": f"Context key '{key}' removed successfully"}
        return {"status": "error", "message": f"Key '{key}' not found in context"}

    def _mcp_info(self) -> Dict:
        """
        Get information about this MCP agent's capabilities.
        
        Returns:
            Dict containing MCP agent information
        """
        return {
            "id": self.mcp_id,
            "name": self.name,
            "version": self.mcp_version,
            "tools": [
                {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
                for name, tool in self.mcp_tools.items()
            ]
        }

    # Override ConversableAgent methods to integrate MCP
    def generate_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        exclude_list: Optional[List[str]] = None,
        **kwargs,
    ) -> Union[str, Dict, None]:
        """
        Generate a reply based on the conversation history and with MCP context.

        This overrides the base ConversableAgent method to integrate MCP context
        into the generation process.

        Args:
            messages: Optional list of messages to process
            sender: The sender agent of the message
            exclude_list: List of function names to exclude from auto-function calling
            **kwargs: Additional keyword arguments

        Returns:
            The generated reply
        """
        # Inject MCP context into the prompt if available
        if messages:
            last_message = messages[-1]
            if "content" in last_message and isinstance(last_message["content"], str):
                # Check if message contains MCP tool calls
                self._process_mcp_tool_calls(last_message)
                
        # For LLM-based generation, handle context in a different way
        # For AutoGen, we can't directly modify system_message since it's a property
        if hasattr(self, "llm_config") and self.llm_config:
            context_summary = self._generate_context_summary()
            
            if context_summary and messages:
                # Instead of modifying system_message, add context in the message list
                context_msg = {
                    "role": "system",
                    "content": f"Current context information:\n{context_summary}"
                }
                
                # Insert the context message at an appropriate position in the conversation
                if len(messages) > 1:
                    # Insert before the last message
                    messages = messages[:-1] + [context_msg] + [messages[-1]]
                else:
                    # Insert before the only message
                    messages = [context_msg] + messages
        
        # Call the parent class method to generate the reply
        reply = super().generate_reply(
            messages=messages, sender=sender, exclude_list=exclude_list, **kwargs
        )
        return reply

    def _generate_context_summary(self) -> str:
        """
        Generate a summary of available context for inclusion in the system message.
        
        Returns:
            String summary of available context
        """
        if not self.context_store:
            return ""
            
        summary_parts = []
        for key, value in self.context_store.items():
            # For complex objects, just indicate their type
            if isinstance(value, dict):
                summary_parts.append(f"- {key}: Dictionary with {len(value)} items")
            elif isinstance(value, list):
                summary_parts.append(f"- {key}: List with {len(value)} items")
            elif isinstance(value, str) and len(value) > 100:
                summary_parts.append(f"- {key}: Text ({len(value)} chars)")
            else:
                summary_parts.append(f"- {key}: {value}")
                
        return "\n".join(summary_parts)

    def _process_mcp_tool_calls(self, message: Dict) -> None:
        """
        Process any MCP tool calls in a message.
        
        This function supports multiple tool call formats:
        1. OpenAI function call format (if present in message)
        2. Explicit MCP call format: mcp.call({...})
        3. Natural language tool call detection (basic)
        
        Args:
            message: The message to process for tool calls
        """
        content = message.get("content", "")
        if not isinstance(content, str):
            return
            
        # Check for tool_calls in the OpenAI message format
        if "tool_calls" in message:
            tool_calls = message.get("tool_calls", [])
            for tool_call in tool_calls:
                try:
                    # Extract tool name and arguments
                    function = tool_call.get("function", {})
                    tool_name = function.get("name")
                    arguments_str = function.get("arguments", "{}")
                    arguments = json.loads(arguments_str)
                    
                    if tool_name in self.mcp_tools:
                        # Execute the tool
                        func = self.mcp_tools[tool_name]["function"]
                        result = func(**arguments)
                        
                        # Store the result in the context
                        result_key = f"result_{uuid.uuid4().hex[:8]}"
                        self.context_store[result_key] = result
                        print(f"Executed tool '{tool_name}' with result: {result}")
                except Exception as e:
                    print(f"Error processing OpenAI tool call: {e}")
        
        # Check for explicit MCP calls in the format mcp.call({...})
        import re
        tool_call_pattern = r"mcp\.call\(([^)]+)\)"
        explicit_calls = re.findall(tool_call_pattern, content)
        for call in explicit_calls:
            try:
                # Parse the tool call arguments
                call_args = json.loads(f"{{{call}}}")
                tool_name = call_args.get("tool")
                arguments = call_args.get("arguments", {})
                
                if tool_name in self.mcp_tools:
                    # Execute the tool
                    func = self.mcp_tools[tool_name]["function"]
                    result = func(**arguments)
                    
                    # Store the result in the context
                    result_key = f"result_{uuid.uuid4().hex[:8]}"
                    self.context_store[result_key] = result
                    print(f"Executed explicit MCP call to '{tool_name}' with result: {result}")
            except Exception as e:
                print(f"Error processing explicit MCP tool call: {e}")
        
        # Add basic natural language detection for common context operations
        # This is a simplified approach - in production, you would use more robust NLP
        content_lower = content.lower()
        
        # Very basic pattern matching for user requests to update context
        if ("add" in content_lower and "to my interests" in content_lower) or \
           ("update my interests" in content_lower):
            try:
                # Extract the interest to add - very simplified regex extraction
                interest_match = re.search(r"add ['\"]?([^'\"]+)['\"]? to my interests", content_lower)
                if interest_match:
                    interest = interest_match.group(1).strip()
                    if "user_preferences" in self.context_store:
                        user_prefs = self.context_store["user_preferences"]
                        if isinstance(user_prefs, dict) and "interests" in user_prefs:
                            if interest not in user_prefs["interests"]:
                                user_prefs["interests"].append(interest)
                                self.update_context("user_preferences", user_prefs)
                                print(f"Added '{interest}' to user interests via natural language detection")
            except Exception as e:
                print(f"Error processing natural language context update: {e}")

    def update_context(self, key: str, value: Any) -> None:
        """
        Update the MCP context with a new key-value pair.
        
        Args:
            key: The context key
            value: The context value
        """
        self.context_store[key] = value
    
    def get_context(self, key: str) -> Any:
        """
        Get a value from the MCP context.
        
        Args:
            key: The context key to retrieve
            
        Returns:
            The context value or None if not found
        """
        return self.context_store.get(key)
    
    def list_available_tools(self) -> List[Dict]:
        """
        Get a list of all available MCP tools.
        
        Returns:
            List of tool definitions
        """
        return [
            {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
            for name, tool in self.mcp_tools.items()
        ]
        
    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute an MCP tool by name with the provided arguments.
        
        Args:
            tool_name: The name of the tool to execute
            **kwargs: Arguments to pass to the tool
            
        Returns:
            The result of the tool execution
            
        Raises:
            ValueError: If the tool is not found
        """
        if tool_name not in self.mcp_tools:
            raise ValueError(f"Tool '{tool_name}' not found")
            
        # Get the tool and its function
        tool = self.mcp_tools[tool_name]
        func = tool["function"]
        
        # Call the function directly without passing self again (it's already bound)
        return func(**kwargs)
