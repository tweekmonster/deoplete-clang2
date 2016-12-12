" Fixes the built-in highlighting.
syn region objcMethodCall start=/\[/ end=/\]/ keepend contains=objcMethodCall,objcBlocks,@objcObjCEntities,@objcCEntities
