"""
Classes for the sidebar generation. 
"""
from typing import Iterable, List, Optional, Sequence, Tuple, Type, Union
from twisted.web.iweb import IRequest, ITemplateLoader
from twisted.web.template import TagLoader, renderer, tags, Tag, Element

from pydoctor import epydoc2stan
from pydoctor.model import Attribute, Class, Function, Documentable, Module, Package
from pydoctor.templatewriter import util, TemplateLookup, TemplateElement

class SideBar(TemplateElement):
    """
    Sidebar. 

    Contains:
        - the object docstring table of contents if titles are defined
        - for classes: 
            - information about the contents of the current class and parent module/package. 
        - for modules/packages:
            - information about the contents of the module and parent package. 
    """

    #TODO: add the equivalent of reStructuredText directive .. contents automatically.

    filename = 'sidebar.html'

    def __init__(self, docgetter: util.DocGetter, 
                 loader: ITemplateLoader, ob: Documentable, 
                 template_lookup: TemplateLookup):
        super().__init__(loader)
        self.ob = ob
        self.template_lookup = template_lookup
        self.docgetter = docgetter


    @renderer
    def sections(self, request: IRequest, tag: Tag) -> Sequence[Element]:
        """
        Sections are a SideBarSection elements, separated by <hr />
        """
        r = []   
        if isinstance(self.ob, (Package, Module)):
            if isinstance(self.ob, Package):
                r.append(SideBarSection(docgetter=self.docgetter, ob=self.ob,
                                    loader=TagLoader(tag), 
                                    template_lookup=self.template_lookup, first=True))
            else:
                r.append(SideBarSection(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob.module, 
                             template_lookup=self.template_lookup, first=True))
            if self.ob.parent:
                r.append(SideBarSection(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob.parent, 
                             template_lookup=self.template_lookup))
        else:
            r.append(SideBarSection(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob, 
                         template_lookup=self.template_lookup, first=True))
            
            if self.ob.module.name == "__init__" and self.ob.module.parent:
                r.append(SideBarSection(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob.module.parent, 
                             template_lookup=self.template_lookup))
            else:
                r.append(SideBarSection(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob.module, 
                             template_lookup=self.template_lookup))
        return r

class SideBarSection(Element):
    """
    Main sidebar section. 
    
    The sidebar typically contains two C{SideBarSection}: one for the documented object and one for it's parent. 
    Root modules have only one section. 
    """
    #TODO: Add a current_obj parameter in order to disable the expandable item for 
    # the current obj inside the paremts items and make it gray or something. 
    # so it's clear that it's the one selected currently. 
    
    def __init__(self, docgetter: util.DocGetter, loader: ITemplateLoader, ob: Documentable, 
                 template_lookup: TemplateLookup, first: bool = False):
        super().__init__(loader)
        self.ob = ob
        self.template_lookup = template_lookup
        self.docgetter = docgetter
        self._first = first
    
    @renderer
    def separator(self, request: IRequest, tag: Tag) -> Tag:
        # mypy gets error: Returning Any from function declared to return "Tag"
        return tag.clear()(tags.hr) if not self._first else tag.clear() # type: ignore[no-any-return]

    @renderer
    def kind(self, request: IRequest, tag: Tag) -> Tag:
        # mypy gets error: Returning Any from function declared to return "Tag"
        return tag.clear()(self.ob.kind) # type: ignore[no-any-return]

    @renderer
    def name(self, request: IRequest, tag: Tag) -> Tag:
        name = self.ob.name
        if name == "__init__" and self.ob.parent:
            name = self.ob.parent.name
        # mypy gets error: Returning Any from function declared to return "Tag"
        return tag.clear()(name) # type: ignore[no-any-return]

    @renderer
    def content(self, request: IRequest, tag: Tag) -> Element:
        if isinstance(self.ob, (Package, Module)):
            if isinstance(self.ob, Package):
                return PackageContent(docgetter=self.docgetter,
                                    loader=TagLoader(tag), 
                                    package=self.ob, 
                                    init_module=self.ob.module, 
                                    template_lookup=self.template_lookup)
            else:
                return ObjContent(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob.module, 
                             template_lookup=self.template_lookup)

        else:
            return ObjContent(docgetter=self.docgetter, loader=TagLoader(tag), ob=self.ob, 
                         template_lookup=self.template_lookup)

class ObjContent(Element):
    """
    Object content displayed on the sidebar. 

    Each L{SideBarSection} object uses one of these in the L{SideBarSection.content} renderer. 

    Composed by L{ContentList} elements. 
    """

    #TODO: Hide the childrenKindTitle if they are all private and show ptivate is off -> need JS

    def __init__(self, docgetter: util.DocGetter, loader: ITemplateLoader, ob: Documentable, 
                 template_lookup: TemplateLookup, level: int = 0, depth: int = 3):

        super().__init__(loader)
        self.ob = ob
        self.template_lookup = template_lookup
        self.docgetter = docgetter

        self._depth = depth
        self._level = level + 1

        self.classList = self._getListOf(Class)
        self.functionList = self._getListOf(Function)
        self.variableList = self._getListOf(Attribute)
        self.subModuleList = self._getListOf((Module, Package))

        self.inheritedFunctionList = self._getListOf(Function, inherited=True) if isinstance(self.ob, Class) else None
        self.inheritedVariableList = self._getListOf(Attribute, inherited=True) if isinstance(self.ob, Class) else None

    def children(self, inherited: bool = False) -> Optional[List[Documentable]]:
        if inherited:
            if isinstance(self.ob, Class):
                children : List[Documentable] = []
                for baselist in util.nested_bases(self.ob):
                    #  If the class has super class
                    if len(baselist) >= 2:
                        attrs = util.unmasked_attrs(baselist)
                        if attrs:
                            children.extend(attrs)
                return sorted(
                    [o for o in children if o.isVisible],
                     key=lambda o:-o.privacyClass.value)
            else:
                return None
        else:
            return sorted(
                [o for o in self.ob.contents.values() if o.isVisible],
                 key=lambda o:-o.privacyClass.value)

    def expand_list(self, list_type: Union[Type[Documentable], 
                                            Tuple[Type[Documentable], ...]]) -> bool:
        """
        Should the list items be expandable?
        """
        
        can_be_expanded = False

        # Classes, modules and packages can be expanded in the sidebar. 
        if isinstance(list_type, type) and issubclass(list_type, (Class, Module, Package)):
            can_be_expanded = True
        elif isinstance(list_type, tuple) and any([issubclass(t, (Class, Module, Package)) for t in list_type]):
            can_be_expanded = True
        
        return self._level < self._depth and can_be_expanded

    @renderer
    def docstringToc(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        
        toc = self.docgetter.get_toc(self.ob)
        if toc:
            # mypy gets error: Returning Any from function declared to return "Union[Tag, str]"
            return tag.fillSlots(titles=toc) # type: ignore[no-any-return]
        else:
            return ""

    @renderer
    def classesTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return tag.clear()("Classes") if self.classList else ""

    @renderer
    def classes(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.classList or ""
    
    @renderer
    def functionsTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return (tag.clear()("Functions") if not isinstance(self.ob, Class) 
                else tag.clear()("Methods")) if self.functionList else ""

    @renderer
    def functions(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.functionList or ""
    
    @renderer
    def inheritedFunctionsTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return tag.clear()("Inherited Methods") if self.inheritedFunctionList else ""

    @renderer
    def inheritedFunctions(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.inheritedFunctionList or ""

    @renderer
    def variablesTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return (tag.clear()("Variables")) if self.variableList else ""
    
    @renderer
    def variables(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.variableList or ""

    @renderer
    def inheritedVariablesTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return tag.clear()("Inherited Variables") if self.inheritedVariableList else ""

    @renderer
    def inheritedVariables(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.inheritedVariableList or ""

    @renderer
    def subModulesTitle(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        return tag.clear()("Modules") if self.subModuleList else ""
    
    @renderer
    def subModules(self, request: IRequest, tag: Tag) -> Union[Element, str]:
        return self.subModuleList or ""

    def _getListOf(self, 
                         type_: Union[Type[Documentable], 
                                Tuple[Type[Documentable], ...]],
                         inherited: bool = False) -> Optional[Element]:
        children = self.children(inherited=inherited)
        if children:
            things = [ child for child in children if isinstance(child, type_) ]
            return self._getListFrom(things, expand=self.expand_list(type_))
        else:
            return None
            
    #TODO: ensure not to crash if heterogeneous Documentable types are passed

    def _getListFrom(self, things: Iterable[Documentable], expand: bool) -> Element:
        if things:
            assert self.loader is not None
            return ContentList(ob=self.ob, children=things,
                    loader=ContentList.lookup_loader(self.template_lookup), 
                    docgetter=self.docgetter,
                    expand=expand,
                    nestedContentLoader=self.loader, 
                    template_lookup=self.template_lookup,
                    level_depth=(self._level, self._depth))
        else:
            return None
        

class PackageContent(ObjContent):
    # This class should be deleted once https://github.com/twisted/pydoctor/pull/360/files has been merged

    def __init__(self,  docgetter: util.DocGetter, loader: ITemplateLoader, package: Package, 
                 init_module: Module, template_lookup: TemplateLookup, depth: int = 3, level: int = 0 ):

        self.init_module = init_module
        super().__init__(docgetter=docgetter, loader=loader, 
                         ob=package, template_lookup=template_lookup, depth=depth, level=level)
        
    def init_module_children(self) -> Iterable[Documentable]:
        return sorted(
            [o for o in self.init_module.contents.values() if o.isVisible],
            key=lambda o:-o.privacyClass.value)
    
    def _getListOf(self, type_: Union[Type[Documentable], 
                                Tuple[Type[Documentable], ...]], inherited: bool = False
                  ) -> Optional[Element]:

        sub_modules = [ child for child in self.children() if isinstance(child, type_) and child.name != '__init__' ]
        contents_filtered = [ child for child in self.init_module_children() 
                                          if isinstance(child, type_) ] + sub_modules
        things = contents_filtered

        return self._getListFrom(things, expand=self.expand_list(type_))

class ContentList(TemplateElement):
    """
    List of child objects that share the same kind. 

    One L{ObjContent} element can have up to six C{ContentList}: 
        - classes 
        - functions/methods
        - variables
        - modules
        - inherited variables (todo)
        - inherited methods (todo)
    """
    # one table per module children kind: classes, functions, variables, modules

    filename = 'sidebar-list.html'

    def __init__(self, ob: Documentable, docgetter: util.DocGetter,
                 children: Iterable[Documentable], loader: ITemplateLoader, 
                 expand: bool, nestedContentLoader: ITemplateLoader, template_lookup: TemplateLookup,
                 level_depth: Tuple[int, int]):
        super().__init__(loader)
        self.ob = ob 
        self.children = children

        self._expand = expand
        self._level_depth = level_depth

        self.nestedContentLoader = nestedContentLoader
        self.docgetter = docgetter
        self.template_lookup = template_lookup
    
    @renderer
    def items(self, request: IRequest, tag: Tag) -> Iterable[Element]:
        return [
            ContentItem(
                loader=TagLoader(tag),
                ob=self.ob,
                child=child, 
                docgetter=self.docgetter,
                expand=self._expand, 
                nestedContentLoader=self.nestedContentLoader if self._expand else None,
                template_lookup=self.template_lookup, level_depth=self._level_depth)
            for child in self.children]

class ContentItem(Element):
    """
    L{ContentList} item. 
    """

    #TODO: Show a text like "No members" when an object do not have any members, instead of expanding on an empty div. 

    def __init__(self, loader: ITemplateLoader, ob: Documentable, child: Documentable, docgetter: util.DocGetter,
                 expand: bool, nestedContentLoader: Optional[ITemplateLoader], template_lookup: TemplateLookup,
                 level_depth: Tuple[int, int]):
        
        super().__init__(loader)
        self.child = child
        self.ob = ob

        self._expand = expand
        self._level_depth = level_depth

        self.nestedContentLoader = nestedContentLoader
        self.docgetter = docgetter
        self.template_lookup = template_lookup

    @renderer
    def class_(self, request: IRequest, tag: Tag) -> str:
        class_ = ''
        # Uncomment if we want to keep same style as in the summary table. 
        # I found it a little bit too colorful. 
        # class_ += 'base' + self.child.css_class + ' '
        if self.child.isPrivate:
            class_ += "private"
        return class_

    def nested_contents(self) -> Element:
        assert self.nestedContentLoader is not None

        if isinstance(self.child, (Package, Module)):
            if isinstance(self.child, Package):
                return PackageContent(docgetter=self.docgetter,
                                    loader=self.nestedContentLoader, 
                                    package=self.child, 
                                    init_module=self.child.module, 
                                    template_lookup=self.template_lookup,
                                    level=self._level_depth[0], 
                                    depth=self._level_depth[1])
            else:
                return ObjContent(docgetter=self.docgetter, loader=self.nestedContentLoader, ob=self.child.module, 
                             template_lookup=self.template_lookup, level=self._level_depth[0], 
                                    depth=self._level_depth[1])

        else:
            return ObjContent(docgetter=self.docgetter, loader=self.nestedContentLoader, ob=self.child, 
                         template_lookup=self.template_lookup, level=self._level_depth[0], 
                                    depth=self._level_depth[1])
    
    @renderer
    def expandableItem(self, request: IRequest, tag: Tag) -> Union[Tag, Element]:
        if self._expand:
            return ExpandableItem(TagLoader(tag), self.child, self.nested_contents())
        else:
            return Tag('transparent')

    @renderer
    def linkOnlyItem(self, request: IRequest, tag: Tag) -> Union[Tag, Element]:
        if not self._expand:
            return LinkOnlyItem(TagLoader(tag), self.child)
        else:
            return Tag('transparent')

class LinkOnlyItem(Element):
    """
    Sidebar leaf item.

    Used by L{ContentItem.linkOnlyItem}
    """

    def __init__(self, loader: ITemplateLoader, child: Documentable):
        super().__init__(loader)
        self.child = child
    @renderer
    def name(self, request: IRequest, tag: Tag) -> Tag:
        return Tag('code', children=[epydoc2stan.taglink(self.child, self.child.url, self.child.name)])

class ExpandableItem(LinkOnlyItem):
    """
    Sidebar expandable item.

    Used by L{ContentItem.expandableItem}
    """

    last_ExpandableItem_id = 0

    def __init__(self, loader: ITemplateLoader, child: Documentable, contents: Element):
        super().__init__(loader, child)
        self._contents =  contents
        ExpandableItem.last_ExpandableItem_id += 1
        self._id = ExpandableItem.last_ExpandableItem_id
    @renderer
    def contents(self, request: IRequest, tag: Tag) -> Element:
        return self._contents
    @renderer
    def expandableItemId(self, request: IRequest, tag: Tag) -> str:
        return f"expandableItemId{self._id}"

